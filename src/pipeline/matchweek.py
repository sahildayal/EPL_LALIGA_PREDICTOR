"""
The three matchweek jobs.

    Friday   collect -> price -> stake -> log
    Sat/Sun  read-only price snapshot (CLV capture)
    Monday   settle -> void -> score -> report

**Fail closed.** If any required data source is unavailable, we place zero bets,
log the reason and exit non-zero. A missed matchweek costs a little sample size;
betting on stale or partial prices costs money and corrupts the experiment that
the whole season exists to run. There is no "bet the half we could price" path.
"""
import json
import os
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.data.canonical_teams import canonical
from src.data.odds_api import fetch_fair_prices, OddsUnavailable
from src.market import arms as arms_mod
from src.market import ledger
from src.market.grading import MARKET_1X2, MARKET_TOTALS, MARKET_BTTS
from src.market.edge import Opportunity
from src.market.kalshi_client import KalshiClient, KalshiUnavailable
from src.models.implied_goals import derive_markets
from src.pipeline import kalshi_markets as km

LOG_DIR = Path("data/processed/matchweek_logs")
LEAGUES = ("epl", "laliga")

# Only bet fixtures kicking off before the NEXT stake run.
#
# Kalshi lists fixtures roughly two weeks ahead, so without this a Friday run
# stakes matches up to 14 days out and the following Friday stakes several of
# them again — double exposure on one outcome, silently doubling the per-fixture
# cap. Seven days is exactly the gap between scheduled runs, so each fixture
# falls inside exactly one window.
#
# Eight days would NOT be safe: Friday + 8 reaches into the next Friday's
# window, and the Friday/Saturday fixtures in the overlap would be bet twice.
#
# It also keeps CLV meaningful. Closing prices are captured by the weekend
# snapshot jobs, so a bet placed 14 days early would be compared against a
# "closing" price a fortnight later, measuring something quite different from a
# bet placed two days out.
BET_WINDOW_DAYS = 7


class PipelineAborted(RuntimeError):
    """Raised when required data is missing. No bets are placed."""


@dataclass
class RunReport:
    job: str
    started_utc: str
    ok: bool = False
    errors: list = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def write(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = self.started_utc.replace(":", "").replace("-", "")[:15]
        path = LOG_DIR / f"{stamp}_{self.job}.json"
        path.write_text(json.dumps(self.__dict__, indent=2, default=str))
        return path


def _now():
    return datetime.now(timezone.utc).isoformat()


# --- Data collection ---------------------------------------------------------

def collect_kalshi() -> list:
    """Fetches and normalises every in-scope Kalshi market. Raises if unavailable."""
    client = KalshiClient()
    raw, per_ticker = [], {}
    for ticker in km.all_series_tickers():
        try:
            resp = client._request(
                "GET", "/trade-api/v2/markets",
                params={"series_ticker": ticker, "status": "open", "limit": 200})
        except Exception as exc:
            raise KalshiUnavailable(f"Kalshi market fetch failed for {ticker}: {exc}") from exc
        if resp.status_code != 200:
            raise KalshiUnavailable(f"Kalshi returned {resp.status_code} for {ticker}")
        markets = resp.json().get("markets", [])
        per_ticker[ticker] = len(markets)
        for m in markets:
            m.setdefault("series_ticker", ticker)
            raw.append(m)
    if not raw:
        # 2026-09-04: a scheduled run aborted here with every ticker reporting
        # zero, while an unauthenticated curl of the same tickers moments
        # later returned that week's fixtures fine — a transient blip on
        # Kalshi's side (or their rate limiting), not a code or credential
        # problem, since a same-day retry succeeded cleanly. Printing the
        # per-ticker breakdown only in this empty case, so the next occurrence
        # shows up in the run log without adding noise to every normal run.
        print(f"[kalshi] every series returned zero open markets: {per_ticker}")
    return km.normalise(raw)


def within_bet_window(markets: list, now=None, days: int = BET_WINDOW_DAYS) -> tuple:
    """
    Splits markets into (in_window, outside, undated).

    The window is half-open: `now <= kickoff < now + days`.

    Both bounds matter. The lower one excludes fixtures that have already kicked
    off — Kalshi can leave a market open into the match, and betting a game in
    progress is not the experiment we are running. The upper one is EXCLUSIVE so
    that consecutive runs cannot both claim a fixture landing exactly on the
    boundary; an inclusive bound would double-stake it.

    A market with no parseable kickoff is UNDATED and not bet. We cannot show it
    falls in exactly one window, so betting it risks the double exposure this
    window exists to prevent, and the standing rule is that an unverifiable
    input means no bet rather than a guess.
    """
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    keep, outside, undated = [], [], []

    for m in markets:
        raw = m.get("kickoff")
        if not raw:
            undated.append(m)
            continue
        try:
            ko = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            undated.append(m)
            continue
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        (keep if now <= ko < horizon else outside).append(m)

    return keep, outside, undated


def _pre_kickoff(markets: list, now=None) -> list:
    """
    Markets whose fixture hasn't started, keeping only those with a parseable
    kickoff.

    Kalshi leaves a market listed after kickoff, and an in-play ask reflects
    the live score rather than the pre-match line the model priced. Mixed into
    telemetry, one goal can produce a double-digit "edge" against a stale fair
    value that has nothing to do with a real pre-kickoff mispricing.
    `_edge_distribution` on the snapshot job must only see markets this filter
    keeps, or the season's evidence on whether Kalshi ever offers 2%+
    divergence gets contaminated by in-play noise.
    """
    now = now or datetime.now(timezone.utc)
    keep = []
    for m in markets:
        raw = m.get("kickoff")
        if not raw:
            continue
        try:
            ko = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        if now <= ko:
            keep.append(m)
    return keep


def fetch_orderbook(client, ticker: str) -> dict:
    """Raw order book for one market. Raises so the caller can fail that bet closed."""
    resp = client._request("GET", f"/trade-api/v2/markets/{ticker}/orderbook",
                           params={"depth": 50})
    if resp.status_code != 200:
        raise KalshiUnavailable(f"orderbook {ticker} returned {resp.status_code}")
    return resp.json()


def reprice_at_fill(plans: dict, client=None) -> tuple:
    """
    Re-prices every planned bet at the price it could ACTUALLY have been filled
    at, and drops those that no longer clear their arm's threshold.

    The quoted ask is the price of the first contract only. Sizing at the ask and
    then recording the ask assumes infinite depth there, which is false: a live
    example wanted 979 contracts of Elche at $0.30 against 490 resting, filling
    at ~$0.3105. Booking that at $0.30 would put an unobtainable price in the
    ledger and overstate the edge by about a cent — half the 2% edge budget.

    Bets whose book cannot be read, or cannot absorb the stake, are dropped
    rather than booked at an optimistic price. Returns (plans, adjustments).
    """
    from src.market.arms import ARM_CONFIGS
    client = client or KalshiClient()
    out, notes = {}, []

    for arm, ps in plans.items():
        cfg = ARM_CONFIGS[arm]
        kept = []
        for p in ps:
            # Parlays are priced off their legs' quoted asks; walking several
            # books for one synthetic combined price is not meaningful, and the
            # combined ask is already flagged synthetic and penalised.
            if "parlay" in p:
                kept.append(p)
                continue

            bet, opp = p["bet"], p["opportunity"]
            if not opp.ticker:
                notes.append({"arm": arm, "bet": bet.label, "action": "dropped",
                              "reason": "no ticker, cannot verify fill price"})
                continue
            try:
                ladder = km.ask_ladder(fetch_orderbook(client, opp.ticker))
                fill = km.vwap_fill(ladder, bet.stake)
            except Exception as exc:
                notes.append({"arm": arm, "bet": bet.label, "action": "dropped",
                              "reason": f"orderbook unavailable: {exc}"})
                continue
            if fill is None:
                notes.append({"arm": arm, "bet": bet.label, "action": "dropped",
                              "reason": f"book too thin to fill ${bet.stake:.2f}"})
                continue

            filled = Opportunity(
                home=opp.home, away=opp.away, market=opp.market,
                selection=opp.selection, fair_prob=opp.fair_prob,
                ask=fill["vwap"], fair_source=opp.fair_source,
                league=opp.league, kickoff=opp.kickoff, line=opp.line,
                ticker=opp.ticker, sharp_book=opp.sharp_book,
                model_prob=opp.model_prob,
            )
            if filled.net_edge < cfg.min_edge:
                notes.append({
                    "arm": arm, "bet": bet.label, "action": "dropped",
                    "reason": f"edge did not survive slippage: quoted {opp.ask:.4f} "
                              f"-> fill {fill['vwap']:.4f}, net edge "
                              f"{opp.net_edge:.4f} -> {filled.net_edge:.4f}"})
                continue

            if abs(fill["vwap"] - opp.ask) > 1e-9:
                notes.append({
                    "arm": arm, "bet": bet.label, "action": "repriced",
                    "quoted": opp.ask, "fill": fill["vwap"],
                    "contracts": fill["contracts"]})
            bet.price = fill["vwap"]
            bet.fill_contracts = fill["contracts"]
            bet.quoted_ask = opp.ask
            kept.append({**p, "opportunity": filled, "fill": fill})
        out[arm] = kept

    return out, notes


def collect_fair_values() -> dict:
    """
    De-vigged sharp consensus per fixture, keyed (home, away).

    Raises if EITHER league fails. Betting only the league that priced would be
    a silent partial week that looks identical to a normal one in the results.
    """
    fair = {}
    for league in LEAGUES:
        # 'btts' is NOT a valid market on the bulk odds endpoint — requesting it
        # returns 422 and fails the entire run. It is derived below instead.
        data = fetch_fair_prices(league, markets="h2h,totals")
        for fx in data["fixtures"]:
            key = (canonical(fx["home"], strict=False), canonical(fx["away"], strict=False))
            entry = fair.setdefault(key, {})
            h2h = fx["fair"].get("h2h", {})
            if h2h:
                mapped = {}
                for name, p in h2h.items():
                    if name.lower() == "draw":
                        mapped["draw"] = p
                    elif canonical(name, strict=False) == key[0]:
                        mapped["home"] = p
                    elif canonical(name, strict=False) == key[1]:
                        mapped["away"] = p
                if len(mapped) == 3:
                    entry[MARKET_1X2] = mapped
            totals_line = None
            totals = fx["fair"].get("totals", {})
            if totals:
                entry[MARKET_TOTALS] = {
                    ("over" if k.lower().startswith("over") else "under"): v
                    for k, v in totals.items()
                }
                for k in totals:
                    m = re.search(r"(\d+(?:\.\d+)?)", k)
                    if m:
                        totals_line = float(m.group(1))
                        break

            # BTTS is not served by the bulk odds endpoint, so derive it from the
            # sharp 1X2 and totals rather than falling back on our own model.
            # derive_markets returns {} unless the fit reproduces the sharp prices,
            # so a fixture we cannot price coherently is simply not bet.
            if MARKET_1X2 in entry and entry.get(MARKET_TOTALS) and totals_line:
                derived = derive_markets(entry[MARKET_1X2], entry[MARKET_TOTALS],
                                         totals_line=totals_line)
                if derived:
                    entry[MARKET_BTTS] = {"yes": derived["btts_yes"],
                                          "no": derived["btts_no"]}
                    entry["_btts_derived"] = True
                    entry["_implied_lambdas"] = (derived["lambda_home"],
                                                 derived["lambda_away"])
                    # Kept so arm D can rebuild this fixture's scoreline
                    # distribution and price same-game legs jointly rather than
                    # multiplying correlated probabilities together.
                    entry["_implied_rho"] = derived["rho"]
            entry["_book"] = fx.get("source", {}).get("h2h")
    if not fair:
        raise OddsUnavailable("No fair values could be built for either league.")
    return fair


def build_score_matrices(fair: dict) -> dict:
    """
    Rebuilds each fixture's fitted scoreline distribution, keyed (home, away).

    Only fixtures whose sharp 1X2 and totals were solved coherently appear here.
    Arm D refuses to price a same-game parlay without one, which is the intended
    behaviour: no matrix means no honest joint probability.
    """
    from src.models.implied_goals import score_matrix
    out = {}
    for key, entry in fair.items():
        lambdas = entry.get("_implied_lambdas")
        if not lambdas:
            continue
        out[key] = score_matrix(lambdas[0], lambdas[1],
                                entry.get("_implied_rho", -0.05))
    return out


def collect_model_probs(fixture_leagues) -> dict:
    """
    Dixon-Coles probabilities for arm C, keyed (home, away).

    Takes {(home, away): league} and prices each fixture with ITS OWN league's
    model. That pairing is load-bearing, not incidental.

    An earlier version took a bare set of fixtures and, inside each league's
    pass, wrote a probability for every fixture regardless of which league it
    belonged to. La Liga is last in LEAGUES, so its pass overwrote every EPL
    fixture with an identical attack/defence fallback: five different EPL
    fixtures came out with the same home-win probability to sixteen decimal
    places. That is not a prediction, it is a league-average prior wearing the
    shape of one — and it turned a roughly-fair Kalshi ask into an apparent
    35-point edge (Hull v Manchester United: real model 0.125, overwritten
    0.466, ask 0.11). It was invisible for as long as only one league had
    fixtures in the betting window, and would have fired on the first week both
    did, which was the EPL's opening weekend.

    Arm C is a control expected to lose — walk-forward CV found no model beating
    the market in any of 32 fold-league combinations — but it must actually place
    bets for that negative result to mean anything, and they have to be the bets
    the model actually implies.
    """
    import numpy as np
    import pandas as pd
    from src.models.dixon_coles import DixonColes

    csv = Path("data/processed/matches.csv")
    if not csv.exists():
        raise PipelineAborted(f"{csv} missing; run the Phase 1 dataset build first.")
    df = pd.read_csv(csv, parse_dates=["date"])

    out = {}
    for league in LEAGUES:
        wanted = [f for f, lg in fixture_leagues.items() if lg == league]
        if not wanted:
            continue
        sub = df[df.league == league]
        if sub.empty:
            continue
        ref = sub.date.max()
        model = DixonColes(halflife_days=365).fit(
            sub.home.tolist(), sub.away.tolist(),
            sub.home_goals.to_numpy(), sub.away_goals.to_numpy(),
            (ref - sub.date).dt.days.to_numpy())

        # A promoted club with no top-flight history is priced as a weak side —
        # bottom-quintile attack, bottom-quintile defence — rather than as an
        # average one. Applied per missing team, never to a whole fixture.
        fallback = (float(np.percentile(model.attack, 20)),
                    float(np.percentile(model.defence, 80)))
        for home, away in wanted:
            priors = {t: fallback for t in (home, away) if t not in model.index}
            try:
                mk = model.market_probs(home, away, priors=priors)
            except Exception:
                continue
            out[(home, away)] = {
                MARKET_1X2: {"home": mk["home"], "draw": mk["draw"], "away": mk["away"]},
                MARKET_TOTALS: {"over": mk["over_2.5"], "under": 1 - mk["over_2.5"]},
                MARKET_BTTS: {"yes": mk["btts_yes"], "no": mk["btts_no"]},
            }
    return out


# --- Jobs --------------------------------------------------------------------

def _describe_plan(plan: dict) -> dict:
    """One planned wager, flattened for the run log. Singles and parlays differ."""
    if "parlay" in plan:
        p = plan["parlay"]
        return {"label": p.label, "stake": p.stake, "ask": round(p.ask, 4),
                "fair": round(p.fair_prob, 4), "net_edge": round(p.net_edge, 4),
                "legs": len(p.legs), "is_sgp": p.is_sgp,
                "joint_method": p.joint_method}
    bet, opp = plan["bet"], plan["opportunity"]
    return {"label": bet.label, "stake": bet.stake, "ask": bet.price,
            "quoted_ask": bet.quoted_ask, "fill_contracts": bet.fill_contracts,
            "fair": opp.fair_prob, "net_edge": round(opp.net_edge, 4),
            "fair_source": opp.fair_source}


def run_stake(dry_run: bool = False) -> RunReport:
    """Friday: collect, price, stake, log."""
    report = RunReport(job="stake", started_utc=_now())
    try:
        listed = collect_kalshi()
        if not listed:
            raise PipelineAborted("Kalshi listed no in-scope markets.")
        markets, outside, undated = within_bet_window(listed)
        if not markets:
            # Not a failure. Markets ARE listed, they simply kick off later —
            # an international break looks exactly like this, and there are
            # about five a season. Treating a legitimately quiet week as a
            # failure would fire an alert each time and train us to ignore them.
            #
            # Zero markets listed at all is different, and is still an abort
            # above: that is the signature of the parsing bug that silently
            # dropped every market on the exchange.
            report.details = {
                "markets_listed": len(listed),
                "markets": 0,
                "bet_window_days": BET_WINDOW_DAYS,
                "skipped_outside_window": len(outside),
                "skipped_undated": len(undated),
                "dry_run": dry_run,
            }
            report.errors.append(
                f"No bets: Kalshi listed {len(listed)} market(s) but none kick off "
                f"within {BET_WINDOW_DAYS} days. Normal during an international "
                "break or out of season.")
            report.ok = True
            report.write()
            return report
        fair = collect_fair_values()
        # Carry each fixture's league through to the model step, so a fixture is
        # only ever priced by the model that has ratings for its clubs.
        fixture_leagues = {(m["home"], m["away"]): m["league"] for m in markets}
        fixtures = set(fixture_leagues)
        model = collect_model_probs(fixture_leagues)
        matrices = build_score_matrices(fair)

        # Kalshi listed a fixture we could not attach a sharp price to.
        #
        # build_opportunities drops these silently — it looks up (home, away) in
        # the fair-value map and moves on if it misses — so a broken team-name
        # mapping produces exactly the same output as a genuinely quiet week:
        # fewer bets, no error. That is the single most plausible way this
        # pipeline could underperform all season without anyone noticing.
        unpriced = sorted(f for f in fixtures if f not in fair)
        no_matrix = sorted(f for f in fixtures if f in fair and f not in matrices)

        state = ledger.load_state()
        plans = arms_mod.plan_all(markets, fair, model, state=state,
                                  score_matrices=matrices)
        # Book every bet at the price it could actually have been filled at, not
        # at the top-of-book quote it was sized against.
        plans, fill_notes = reprice_at_fill(plans)

        report.details = {
            "markets_listed": len(listed),
            "markets": len(markets),
            "bet_window_days": BET_WINDOW_DAYS,
            "skipped_outside_window": len(outside),
            "skipped_undated": len(undated),
            "fixtures": len(fixtures),
            "fair_fixtures": len(fair),
            "score_matrices": len(matrices),
            "unpriced_fixtures": [list(f) for f in unpriced],
            "fixtures_without_score_matrix": [list(f) for f in no_matrix],
            "planned": {a: len(p) for a, p in plans.items()},
            "fill_adjustments": fill_notes,
            # Reuses the fair values already built above — no extra Odds API call.
            "edge_distribution": _edge_distribution(markets, fair),
            "dry_run": dry_run,
            "bets": {a: [_describe_plan(p) for p in ps] for a, ps in plans.items()},
        }

        # Surfaced as warnings (exit 2), not failures: the bets we COULD price
        # are still good, and refusing the whole week over one unmappable club
        # would cost more than it saves. But it must never pass as a clean run.
        if undated:
            report.errors.append(
                f"{len(undated)} market(s) had no parseable kickoff and were NOT bet. "
                "Without a kickoff we cannot show a fixture falls in exactly one "
                "weekly window, so betting it risks double exposure.")
        if unpriced:
            report.errors.append(
                f"{len(unpriced)} Kalshi fixture(s) had no sharp price and were "
                f"NOT bet: {[list(f) for f in unpriced]}. Usually a team-name "
                "mapping gap in canonical_teams, or an odds feed missing the fixture.")
        if no_matrix:
            report.errors.append(
                f"{len(no_matrix)} fixture(s) priced but with no score matrix, so "
                f"BTTS and same-game parlays were skipped: {[list(f) for f in no_matrix]}. "
                "Usually a missing totals line, or a solve that did not reproduce "
                "the sharp 1X2.")

        if not dry_run:
            placed = {a: arms_mod.place_arm(a, ps, state=state) for a, ps in plans.items()}
            ledger.save_state(state)
            report.details["placed"] = {a: len(r["placed"]) for a, r in placed.items()}

        report.ok = True
    except (KalshiUnavailable, OddsUnavailable, PipelineAborted) as exc:
        report.errors.append(f"{type(exc).__name__}: {exc}")
    except Exception as exc:
        report.errors.append(f"UNEXPECTED {type(exc).__name__}: {exc}")
        report.errors.append(traceback.format_exc())
    report.write()
    return report


def _edge_distribution(markets: list, fair: dict = None) -> dict:
    """
    Where Kalshi sits versus the sharp line right now, whether or not we bet.

    Arms A and B require a 2% net edge and the first live snapshot showed a
    maximum of 1.63% across every listed market, so they may bet rarely. The
    threshold is NOT being tuned to fix that — tuning a threshold until an arm
    starts betting measures the threshold, not the strategy. Instead the
    distribution is recorded on every run, so the question can eventually be
    answered with a month of evidence rather than one far-out reading.

    Recorded at BOTH ends of the week, because they answer different questions.
    The snapshots sample close to kickoff, where divergence is most likely. The
    Friday `stake` run samples the exact moment arms A and B decline to bet —
    without it the ledger records that they planned nothing and gives no way to
    tell "nowhere near the bar" from "missed it by a basis point", which is the
    evidence the season's A-versus-B conclusion has to rest on.

    `fair` may be passed in by a caller that has already built it, so adding
    this to `stake` costs no extra Odds API calls.

    Purely observational. Nothing here influences a bet.
    """
    try:
        from src.market.edge import build_opportunities
        fair = collect_fair_values() if fair is None else fair
        opps = build_opportunities(markets, fair)
        if not opps:
            return {"n": 0}
        edges = sorted((o.net_edge for o in opps), reverse=True)
        mid = len(edges) // 2
        return {
            "n": len(edges),
            "max": round(edges[0], 4),
            "median": round(edges[mid], 4),
            "min": round(edges[-1], 4),
            "count_over": {f"{t:.3f}": sum(1 for e in edges if e >= t)
                           for t in (0.005, 0.01, 0.015, 0.02, 0.03, 0.04)},
        }
    except Exception as exc:
        # Observational only — it must never take down the CLV capture, which is
        # the job's actual purpose.
        return {"error": f"{type(exc).__name__}: {exc}"}


def run_snapshot() -> RunReport:
    """Sat/Sun: read-only price capture for CLV. Never places or settles anything."""
    report = RunReport(job="snapshot", started_utc=_now())
    try:
        markets = collect_kalshi()
        prices = {(m["home"], m["away"], m["market"], m["selection"]): m["ask"]
                  for m in markets}
        stamped = ledger.record_closing_prices(prices)
        report.details = {"markets": len(markets), "stamped": stamped}
        report.details["edge_distribution"] = _edge_distribution(_pre_kickoff(markets))
        report.ok = True
    except Exception as exc:
        report.errors.append(f"{type(exc).__name__}: {exc}")
    report.write()
    return report


def run_settle(results: list = None, voids: list = None) -> RunReport:
    """
    Tuesday: settle finished fixtures, void postponements, score the season.

    Tuesday rather than Monday because a Monday-morning job runs BEFORE Monday
    Night Football, which would leave every MNF bet pending for a full week.

    `results` (a list of MatchResult) and `voids` ((home, away, reason) tuples)
    may be supplied by the caller, which keeps this testable without the network.
    When they are not, they are collected live.
    """
    report = RunReport(job="settle", started_utc=_now())
    try:
        collected = None
        if results is None and voids is None:
            from src.pipeline import results as results_mod
            collected = results_mod.collect()
            results, voids = collected["results"], collected["voids"]

        state = ledger.load_state()
        settled_total, pending_total, parlays_settled = 0, 0, 0
        for r in results or []:
            out = ledger.settle_match(r, state=state)
            settled_total += len(out["settled"])
            pending_total += len(out["pending"])
            parlays_settled += len(out.get("parlays_settled", []))
        voided = []
        for home, away, reason in voids or []:
            voided.extend(ledger.void_fixture(home, away, reason, state=state))
        ledger.save_state(state)

        report.details = {
            "results_seen": len(results or []),
            "settled": settled_total,
            "parlays_settled": parlays_settled,
            "still_pending": pending_total,
            "voided": len(voided),
            "void_fixtures": [list(v) for v in (voids or [])],
            "season": ledger.season_summary(state),
        }
        if collected:
            recon = collected["reconciliation"]
            report.details["reconciliation"] = recon
            report.details["unknown_teams"] = collected["unknown_teams"]
            # A score that changed after we graded it is not a warning to bury in
            # a log file. It means a settled bet may carry the wrong result.
            if recon.get("mismatches"):
                report.errors.append(
                    f"SCORE MISMATCH on {len(recon['mismatches'])} fixture(s) between "
                    f"ESPN and football-data.co.uk: {recon['mismatches']}. "
                    "Settlement completed on the ESPN score; review before trusting these rows.")
            if collected["unknown_teams"]:
                report.errors.append(
                    f"{len(collected['unknown_teams'])} fixture(s) had unrecognised team "
                    f"names and were NOT settled: {collected['unknown_teams']}")

        # Errors here are advisory: settlement itself succeeded. The run is only
        # marked failed if it raised.
        report.ok = True
    except Exception as exc:
        report.errors.append(f"{type(exc).__name__}: {exc}")
        report.errors.append(traceback.format_exc())
    report.write()
    return report
