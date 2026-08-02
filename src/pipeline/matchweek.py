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
from datetime import datetime, timezone
from pathlib import Path

from src.data.canonical_teams import canonical
from src.data.odds_api import fetch_fair_prices, OddsUnavailable
from src.market import arms as arms_mod
from src.market import ledger
from src.market.grading import MARKET_1X2, MARKET_TOTALS, MARKET_BTTS
from src.market.kalshi_client import KalshiClient, KalshiUnavailable
from src.models.implied_goals import derive_markets
from src.pipeline import kalshi_markets as km

LOG_DIR = Path("data/processed/matchweek_logs")
LEAGUES = ("epl", "laliga")


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
    raw = []
    for ticker in km.all_series_tickers():
        try:
            resp = client._request(
                "GET", "/trade-api/v2/markets",
                params={"series_ticker": ticker, "status": "open", "limit": 200})
        except Exception as exc:
            raise KalshiUnavailable(f"Kalshi market fetch failed for {ticker}: {exc}") from exc
        if resp.status_code != 200:
            raise KalshiUnavailable(f"Kalshi returned {resp.status_code} for {ticker}")
        for m in resp.json().get("markets", []):
            m.setdefault("series_ticker", ticker)
            raw.append(m)
    return km.normalise(raw)


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


def collect_model_probs(fixtures) -> dict:
    """
    Dixon-Coles probabilities for arm C.

    Arm C is a control expected to lose — walk-forward CV found no model beating
    the market in any of 32 fold-league combinations — but it must actually place
    bets for that negative result to mean anything.
    """
    import pandas as pd
    from src.models.dixon_coles import DixonColes

    csv = Path("data/processed/matches.csv")
    if not csv.exists():
        raise PipelineAborted(f"{csv} missing; run the Phase 1 dataset build first.")
    df = pd.read_csv(csv, parse_dates=["date"])

    out = {}
    for league in LEAGUES:
        sub = df[df.league == league]
        if sub.empty:
            continue
        ref = sub.date.max()
        model = DixonColes(halflife_days=365).fit(
            sub.home.tolist(), sub.away.tolist(),
            sub.home_goals.to_numpy(), sub.away_goals.to_numpy(),
            (ref - sub.date).dt.days.to_numpy())

        import numpy as np
        fallback = (float(np.percentile(model.attack, 20)),
                    float(np.percentile(model.defence, 80)))
        for home, away in fixtures:
            if home in out or (home, away) in out:
                pass
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
            "fair": opp.fair_prob, "net_edge": round(opp.net_edge, 4),
            "fair_source": opp.fair_source}


def run_stake(dry_run: bool = False) -> RunReport:
    """Friday: collect, price, stake, log."""
    report = RunReport(job="stake", started_utc=_now())
    try:
        markets = collect_kalshi()
        if not markets:
            raise PipelineAborted("Kalshi listed no in-scope markets.")
        fair = collect_fair_values()
        fixtures = {(m["home"], m["away"]) for m in markets}
        model = collect_model_probs(fixtures)
        matrices = build_score_matrices(fair)

        state = ledger.load_state()
        plans = arms_mod.plan_all(markets, fair, model, state=state,
                                  score_matrices=matrices)

        report.details = {
            "markets": len(markets),
            "fixtures": len(fixtures),
            "fair_fixtures": len(fair),
            "score_matrices": len(matrices),
            "planned": {a: len(p) for a, p in plans.items()},
            "dry_run": dry_run,
            "bets": {a: [_describe_plan(p) for p in ps] for a, ps in plans.items()},
        }

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


def run_snapshot() -> RunReport:
    """Sat/Sun: read-only price capture for CLV. Never places or settles anything."""
    report = RunReport(job="snapshot", started_utc=_now())
    try:
        markets = collect_kalshi()
        prices = {(m["home"], m["away"], m["market"], m["selection"]): m["ask"]
                  for m in markets}
        stamped = ledger.record_closing_prices(prices)
        report.details = {"markets": len(markets), "stamped": stamped}
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
