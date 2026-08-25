"""Pipeline tests: market parsing and the fail-closed guarantee."""
from datetime import datetime, timedelta, timezone

import pytest


def _soon(days=2):
    """A kickoff inside the bet window, for mocks that predate it."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

from src.market import ledger
from src.market.grading import MARKET_1X2, MARKET_TOTALS, MARKET_BTTS, MatchResult
from src.pipeline import kalshi_markets as km
from src.pipeline import matchweek


def test_unpriced_kalshi_fixture_is_warned_not_silently_dropped(monkeypatch, tmp_path):
    """
    A Kalshi fixture with no sharp price is skipped by build_opportunities with
    no error, so a broken team-name mapping looks exactly like a quiet week.
    The run must complete (the bets we could price are still good) but must not
    pass as clean.
    """
    from src.market import ledger as _ledger
    from src.pipeline import matchweek as mw
    monkeypatch.setattr(_ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_ledger, "LEDGER_PATH", str(tmp_path / "l.json"))
    monkeypatch.setattr(mw, "LOG_DIR", tmp_path / "logs")

    monkeypatch.setattr(mw, "collect_kalshi", lambda: [
        {"home": "arsenal", "away": "chelsea", "market": "1x2", "selection": "home",
         "ask": 0.40, "league": "epl", "kickoff": _soon()},
        {"home": "liverpool", "away": "everton", "market": "1x2", "selection": "home",
         "ask": 0.40, "league": "epl", "kickoff": _soon()},
    ])
    # Only one of the two fixtures has a sharp price.
    monkeypatch.setattr(mw, "collect_fair_values", lambda: {
        ("arsenal", "chelsea"): {"1x2": {"home": 0.55, "draw": 0.25, "away": 0.20}},
    })
    monkeypatch.setattr(mw, "collect_model_probs", lambda fx: {})

    report = mw.run_stake(dry_run=True)
    assert report.ok                                   # the priced fixture still runs
    assert report.details["unpriced_fixtures"] == [["liverpool", "everton"]]
    assert any("no sharp price" in e for e in report.errors)


def _synthetic_matches(proc):
    """
    Two leagues, disjoint clubs, lopsided records — so a model that knows a
    fixture's clubs must separate them, and one that doesn't cannot.
    """
    import pandas as pd
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    clubs = {"epl": ("ehigh", "emid", "elow"), "laliga": ("lhigh", "lmid", "llow")}
    rows = []
    for week in range(40):
        day = base - timedelta(days=week * 7)
        for league, (high, mid, low) in clubs.items():
            rows += [
                {"league": league, "date": day, "home": high, "away": low,
                 "home_goals": 3, "away_goals": 0},
                {"league": league, "date": day, "home": low, "away": high,
                 "home_goals": 0, "away_goals": 2},
                {"league": league, "date": day, "home": mid, "away": low,
                 "home_goals": 2, "away_goals": 1},
                {"league": league, "date": day, "home": high, "away": mid,
                 "home_goals": 2, "away_goals": 1},
            ]
    proc.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(proc / "matches.csv", index=False)


def test_fixture_is_never_priced_by_another_leagues_model(monkeypatch, tmp_path):
    """
    Every fixture must be priced by the model for ITS OWN league.

    Regression, found live the night before the EPL's opening weekend:
    collect_model_probs looped over every league and, inside each pass, wrote a
    probability for every fixture regardless of league. La Liga is last in
    LEAGUES, so its pass overwrote all EPL fixtures with a single
    attack/defence fallback — five EPL fixtures priced identically to sixteen
    decimal places, turning a roughly-fair Kalshi ask into an apparent
    35-point edge for arm C. Latent for as long as only one league had
    fixtures in the betting window.
    """
    from src.pipeline import matchweek as mw

    _synthetic_matches(tmp_path / "data" / "processed")
    monkeypatch.chdir(tmp_path)

    probs = mw.collect_model_probs({
        ("ehigh", "elow"): "epl",
        ("elow", "ehigh"): "epl",
        ("lhigh", "llow"): "laliga",
    })

    strong = probs[("ehigh", "elow")][MARKET_1X2]["home"]
    weak = probs[("elow", "ehigh")][MARKET_1X2]["home"]

    # Under the bug both EPL fixtures carried the La Liga model's fallback and
    # were byte-identical. The strong side at home must dominate the weak one.
    assert strong != weak
    assert strong > weak + 0.25, f"EPL fixtures priced alike: {strong} vs {weak}"

    # And the La Liga fixture in the same call is still priced by its own model.
    assert probs[("lhigh", "llow")][MARKET_1X2]["home"] > 0.5


def test_model_probs_skips_leagues_with_no_fixtures(monkeypatch, tmp_path):
    """Only leagues actually in the window are fitted — no wasted Dixon-Coles fit."""
    from src.pipeline import matchweek as mw

    _synthetic_matches(tmp_path / "data" / "processed")
    monkeypatch.chdir(tmp_path)

    probs = mw.collect_model_probs({("ehigh", "elow"): "epl"})
    assert set(probs) == {("ehigh", "elow")}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ledger, "LEDGER_PATH", str(tmp_path / "season_ledger.json"))
    monkeypatch.setattr(matchweek, "LOG_DIR", tmp_path / "logs")
    yield


def raw(ticker, series, title, yes_ask=0.45, sub=None, **kw):
    return {"ticker": ticker, "series_ticker": series, "title": title,
            "yes_sub_title": sub, "yes_ask_dollars": yes_ask,
            "status": "open", **kw}


# --- Real Kalshi payload shapes ---------------------------------------------
#
# Every fixture below is copied from a live 2026-08-07 API response. The tests
# that already existed used titles like "Arsenal vs Chelsea", which Kalshi never
# sends — the real format carries a trailing question ("Winner?"). That is
# precisely why the suite was green while production parsed nothing.

def live(ticker, series, title, sub, yes_ask):
    """A market shaped exactly as Kalshi returns it, prices as decimal strings."""
    return {"ticker": ticker, "series_ticker": series, "title": title,
            "yes_sub_title": sub, "no_sub_title": sub,
            "yes_ask_dollars": yes_ask, "status": "active",
            "event_ticker": ticker.rsplit("-", 1)[0]}


ARS_COV = [
    live("KXEPLGAME-26AUG21ARSCOV-ARS", "KXEPLGAME", "Arsenal vs Coventry Winner?", "Arsenal", "0.8100"),
    live("KXEPLGAME-26AUG21ARSCOV-COV", "KXEPLGAME", "Arsenal vs Coventry Winner?", "Coventry", "0.0800"),
    live("KXEPLGAME-26AUG21ARSCOV-TIE", "KXEPLGAME", "Arsenal vs Coventry Winner?", "Tie", "0.1400"),
]


def test_real_kalshi_title_parses():
    """
    Regression. The away capture group is greedy over letters, so
    "Arsenal vs Coventry Winner?" yielded "Coventry Winner", canonical() raised,
    and parse_teams returned (None, None). Every 1X2 market on the exchange was
    dropped, and the pipeline reported "Kalshi listed no in-scope markets" —
    indistinguishable from the season not having started.
    """
    assert km.parse_teams(ARS_COV[0]) == ("arsenal", "coventry")


def test_real_fixture_yields_three_distinct_selections():
    out = km.normalise(ARS_COV)
    assert len(out) == 3
    assert {o["selection"] for o in out} == {"home", "draw", "away"}
    by_sel = {o["selection"]: o["ask"] for o in out}
    assert by_sel["home"] == pytest.approx(0.81)
    assert by_sel["away"] == pytest.approx(0.08)
    assert by_sel["draw"] == pytest.approx(0.14)


def test_decimal_string_prices_are_not_scaled():
    """yes_ask_dollars arrives as a STRING in dollars. 0.81 must not become 81."""
    out = km.normalise([ARS_COV[0]])
    assert 0.0 < out[0]["ask"] < 1.0


def test_shared_first_word_does_not_flip_the_side():
    """
    'Real Betis vs Real Sociedad': both clubs begin "Real". A removed fallback
    matched on the first word of a club's name, so the AWAY contract resolved to
    "home" — staking against the very team the contract pays on.
    """
    fixture = [
        live("KXLALIGAGAME-26AUG21RBBRSO-RBB", "KXLALIGAGAME",
             "Real Betis vs Real Sociedad Winner?", "Real Betis", "0.4900"),
        live("KXLALIGAGAME-26AUG21RBBRSO-RSO", "KXLALIGAGAME",
             "Real Betis vs Real Sociedad Winner?", "Real Sociedad", "0.3400"),
    ]
    out = {o["selection"]: o for o in km.normalise(fixture)}
    assert out["home"]["ask"] == pytest.approx(0.49)
    assert out["away"]["ask"] == pytest.approx(0.34)


def test_title_alone_cannot_decide_the_side():
    """
    The title names BOTH clubs, so falling back to it would resolve all three
    contracts of a fixture to the same side. No subtitle means no bet.
    """
    m = live("KXEPLGAME-X-ARS", "KXEPLGAME", "Arsenal vs Coventry Winner?", None, "0.8100")
    assert km.normalise([m]) == []


def test_alias_resolves_through_the_trailing_trim():
    """Kalshi says 'Vallecano'; the canonical club is 'rayo vallecano'."""
    m = live("KXLALIGAGAME-X-RAY", "KXLALIGAGAME",
             "Sevilla vs Vallecano Winner?", "Vallecano", "0.2900")
    out = km.normalise([m])
    assert len(out) == 1
    assert out[0]["away"] == "rayo vallecano" and out[0]["selection"] == "away"


def test_longest_match_wins_so_a_club_is_never_truncated():
    """
    Trimming tries LONGEST first. "Manchester United Winner" must resolve at
    "Manchester United" and never reach a bare "Manchester".
    """
    assert km._resolve_trailing("Manchester United Winner") == "manchester united"
    assert km._resolve_trailing("Real Sociedad Winner") == "real sociedad"


def test_unresolvable_trailing_text_returns_none():
    assert km._resolve_trailing("Definitely Not A Club") is None


# --- Fill realism ------------------------------------------------------------
#
# Levels below are the real KXLALIGAGAME-26AUG17DEPELC-ELC book on 2026-08-07.
# Kalshi quotes the YES ask from the resting NO side, so buying YES at p matches
# a NO order at (1 - p).

ELC_BOOK = {"orderbook_fp": {"no_dollars": [
    ["0.7000", "490.00"],    # -> buy YES @ 0.30
    ["0.6900", "201.00"],    # -> 0.31
    ["0.6800", "1552.00"],   # -> 0.32
    ["0.6700", "6776.00"],   # -> 0.33
]}}


def test_ask_ladder_reads_the_no_side():
    """
    Reading yes_dollars would give the resting BIDS — what someone would pay us,
    the wrong side of the spread — making every bet look cheaper than it is.
    """
    ladder = km.ask_ladder(ELC_BOOK)
    assert ladder[0] == (0.30, 490.0)
    assert [p for p, _ in ladder] == sorted(p for p, _ in ladder)


def test_small_order_fills_at_the_quote():
    fill = km.vwap_fill(km.ask_ladder(ELC_BOOK), 100.0)
    assert fill["vwap"] == pytest.approx(0.30)


def test_large_order_walks_the_book():
    """
    The live case: a $293.76 stake at a quoted $0.30 against only 490 contracts
    resting there. The true fill is $0.3076 — 0.76 cents of slippage, which is
    over a third of the entire 2% edge budget. Booking it at the quote would
    record a price that was never obtainable.
    """
    fill = km.vwap_fill(km.ask_ladder(ELC_BOOK), 293.76)
    assert fill["vwap"] == pytest.approx(0.307632, abs=1e-5)
    assert fill["contracts"] == pytest.approx(954.9, abs=0.5)
    assert fill["spent"] == pytest.approx(293.76, abs=0.01)


def test_book_too_thin_returns_none():
    """
    A partial fill is a different bet from the one Kelly sized. Quietly shrinking
    the stake would override the staking rule without saying so.
    """
    thin = {"orderbook_fp": {"no_dollars": [["0.7000", "10.00"]]}}
    assert km.vwap_fill(km.ask_ladder(thin), 500.0) is None


def test_empty_book_returns_none():
    assert km.vwap_fill([], 100.0) is None
    assert km.vwap_fill(km.ask_ladder({"orderbook_fp": {}}), 100.0) is None


def test_reprice_drops_a_bet_whose_edge_dies_in_the_slippage(monkeypatch):
    """
    A bet sized on a 2.1% quoted edge that fills 1c worse is no longer a bet the
    arm would have taken. It must be dropped, not booked at the quote.
    """
    from src.market.arms import ARM_A
    from src.market.edge import Opportunity
    from src.market.grading import Bet

    opp = Opportunity(home="a", away="b", market=MARKET_1X2, selection="home",
                      fair_prob=0.55, ask=0.50, fair_source="sharp_consensus",
                      ticker="TKR")
    bet = Bet(market=MARKET_1X2, selection="home", home="arsenal", away="chelsea",
              stake=300.0, price=0.50)
    monkeypatch.setattr(matchweek, "fetch_orderbook",
                        lambda c, t: {"orderbook_fp": {"no_dollars": [
                            ["0.5000", "100.00"], ["0.4000", "100000.00"]]}})
    plans, notes = matchweek.reprice_at_fill(
        {ARM_A: [{"bet": bet, "opportunity": opp, "stake_plan": None}]}, client=object())
    assert plans[ARM_A] == []
    assert notes and "did not survive slippage" in notes[0]["reason"]


def test_reprice_records_the_fill_price_on_the_bet(monkeypatch):
    from src.market.arms import ARM_A
    from src.market.edge import Opportunity
    from src.market.grading import Bet

    opp = Opportunity(home="a", away="b", market=MARKET_1X2, selection="home",
                      fair_prob=0.70, ask=0.40, fair_source="sharp_consensus",
                      ticker="TKR")
    bet = Bet(market=MARKET_1X2, selection="home", home="arsenal", away="chelsea",
              stake=100.0, price=0.40)
    monkeypatch.setattr(matchweek, "fetch_orderbook",
                        lambda c, t: {"orderbook_fp": {"no_dollars": [
                            ["0.6000", "100.00"], ["0.5900", "100000.00"]]}})
    plans, notes = matchweek.reprice_at_fill(
        {ARM_A: [{"bet": bet, "opportunity": opp, "stake_plan": None}]}, client=object())
    kept = plans[ARM_A][0]["bet"]
    assert kept.price > 0.40                    # true fill, worse than the quote
    assert kept.quoted_ask == 0.40              # and the quote is preserved
    assert kept.fill_contracts > 0


def test_unreadable_book_drops_the_bet_rather_than_booking_the_quote(monkeypatch):
    from src.market.arms import ARM_A
    from src.market.edge import Opportunity
    from src.market.grading import Bet

    opp = Opportunity(home="a", away="b", market=MARKET_1X2, selection="home",
                      fair_prob=0.70, ask=0.40, fair_source="sharp_consensus",
                      ticker="TKR")
    bet = Bet(market=MARKET_1X2, selection="home", home="arsenal", away="chelsea",
              stake=100.0, price=0.40)
    def boom(c, t):
        raise RuntimeError("503")
    monkeypatch.setattr(matchweek, "fetch_orderbook", boom)
    plans, notes = matchweek.reprice_at_fill(
        {ARM_A: [{"bet": bet, "opportunity": opp, "stake_plan": None}]}, client=object())
    assert plans[ARM_A] == []
    assert "orderbook unavailable" in notes[0]["reason"]


# --- Bet window --------------------------------------------------------------

from datetime import datetime, timedelta, timezone


def _mk(days_ahead, **kw):
    ko = (datetime(2026, 8, 14, 9, tzinfo=timezone.utc)
          + timedelta(days=days_ahead)).isoformat().replace("+00:00", "Z")
    return {"home": "arsenal", "away": "chelsea", "market": MARKET_1X2,
            "selection": "home", "ask": 0.4, "kickoff": ko, **kw}


NOW = datetime(2026, 8, 14, 9, tzinfo=timezone.utc)


def test_window_keeps_the_coming_week_and_drops_the_rest():
    keep, far, undated = matchweek.within_bet_window(
        [_mk(1), _mk(6), _mk(9), _mk(14)], now=NOW)
    assert len(keep) == 2 and len(far) == 2 and undated == []


def test_consecutive_runs_never_overlap():
    """
    The whole point of the window. Kalshi lists ~14 days ahead, so without this
    a Friday run stakes fixtures the NEXT Friday run would stake again --
    double exposure on one outcome, silently doubling the per-fixture cap.

    Eight days would not be safe: Friday + 8 reaches into the next Friday's
    window, so the fixtures in the overlap get bet twice.
    """
    fixtures = [_mk(d) for d in range(0, 15)]
    week1, _, _ = matchweek.within_bet_window(fixtures, now=NOW)
    week2, _, _ = matchweek.within_bet_window(fixtures, now=NOW + timedelta(days=7))
    assert week1 and week2
    assert not ({m["kickoff"] for m in week1} & {m["kickoff"] for m in week2})


def test_undated_market_is_never_bet():
    """No kickoff means we cannot prove it falls in exactly one window."""
    keep, far, undated = matchweek.within_bet_window(
        [_mk(1), {"home": "a", "away": "b", "market": MARKET_1X2, "ask": 0.4}], now=NOW)
    assert len(keep) == 1 and len(undated) == 1


def test_pre_kickoff_drops_in_play_markets():
    """
    Kalshi leaves a market listed after kickoff, but an in-play ask reflects
    the live score, not the pre-match line the model priced against. Snapshot
    telemetry must not let that masquerade as a real divergence.
    """
    started = _mk(-1)
    upcoming = _mk(1)
    far_out = _mk(30)
    kept = matchweek._pre_kickoff([started, upcoming, far_out], now=NOW)
    assert kept == [upcoming, far_out]


def test_pre_kickoff_drops_undated_markets():
    kept = matchweek._pre_kickoff(
        [{"home": "a", "away": "b", "market": MARKET_1X2, "ask": 0.4}], now=NOW)
    assert kept == []


def test_quiet_week_is_a_warning_not_a_failure(monkeypatch):
    """
    Markets listed but all kicking off later is a normal week during an
    international break — about five a season. Failing would fire an alert each
    time and train us to ignore them. Zero markets listed at all IS still a
    failure: that is the signature of the parsing bug that silently dropped
    every market on the exchange.
    """
    far = dict(_mk(0), kickoff=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
    monkeypatch.setattr(matchweek, "collect_kalshi", lambda: [far])
    rep = matchweek.run_stake(dry_run=True)
    assert rep.ok                                        # not a failure
    assert any("none kick off within" in e for e in rep.errors)   # but still visible
    assert rep.details["markets_listed"] == 1 and rep.details["markets"] == 0


def test_no_markets_at_all_is_still_a_failure(monkeypatch):
    monkeypatch.setattr(matchweek, "collect_kalshi", lambda: [])
    rep = matchweek.run_stake(dry_run=True)
    assert not rep.ok
    assert any("no in-scope markets" in e for e in rep.errors)


def test_unparseable_kickoff_is_undated_not_kept():
    keep, _, undated = matchweek.within_bet_window([_mk(1, kickoff="not a date")], now=NOW)
    assert keep == [] and len(undated) == 1


# --- Series safety ----------------------------------------------------------

def test_laliga2_is_excluded():
    """KXLALIGA2* is the Spanish SECOND division. Betting it would be a real loss."""
    assert km.is_excluded("KXLALIGA2GAME-ABC")
    assert km.is_excluded("KXLALIGA2TOTAL-ABC")
    assert not km.is_excluded("KXLALIGAGAME-ABC")


def test_halves_are_excluded():
    assert km.is_excluded("KXEPL1HTOTAL-X") and km.is_excluded("KXEPL2H-X")


def test_series_lookup_is_exact_not_prefix():
    lookup = km.series_lookup()
    assert lookup["KXLALIGAGAME"] == ("laliga", MARKET_1X2)
    assert "KXLALIGA2GAME" not in lookup


def test_all_six_in_scope_series_present():
    assert len(km.all_series_tickers()) == 6


# --- Parsing ----------------------------------------------------------------

def test_parses_1x2_home_selection():
    out = km.normalise([raw("KXEPLGAME-ARSCHE", "KXEPLGAME",
                            "Arsenal vs Chelsea", sub="Arsenal")])
    assert len(out) == 1
    assert out[0]["home"] == "arsenal" and out[0]["away"] == "chelsea"
    assert out[0]["selection"] == "home" and out[0]["market"] == MARKET_1X2


def test_parses_draw_and_away():
    draw = km.normalise([raw("KXEPLGAME-1", "KXEPLGAME", "Arsenal vs Chelsea", sub="Draw")])
    away = km.normalise([raw("KXEPLGAME-2", "KXEPLGAME", "Arsenal vs Chelsea", sub="Chelsea")])
    assert draw[0]["selection"] == "draw"
    assert away[0]["selection"] == "away"


def test_canonicalises_team_names_from_kalshi():
    out = km.normalise([raw("KXEPLGAME-X", "KXEPLGAME",
                            "Man United vs Nott'm Forest", sub="Man United")])
    assert out[0]["home"] == "manchester united"
    assert out[0]["away"] == "nottingham forest"


def test_totals_produces_both_sides_when_no_ask_present():
    out = km.normalise([raw("KXEPLTOTAL-X", "KXEPLTOTAL", "Arsenal vs Chelsea",
                            yes_ask=0.55, sub="Over 2.5", no_ask_dollars=0.47)])
    sels = {(o["selection"], o["line"], o["ask"]) for o in out}
    assert ("over", 2.5, 0.55) in sels
    assert ("under", 2.5, 0.47) in sels


def test_btts_produces_yes_and_no():
    out = km.normalise([raw("KXEPLBTTS-X", "KXEPLBTTS", "Arsenal vs Chelsea",
                            yes_ask=0.60, no_ask_dollars=0.42)])
    assert {o["selection"] for o in out} == {"yes", "no"}


def test_cents_prices_are_converted():
    out = km.normalise([raw("KXEPLGAME-X", "KXEPLGAME", "Arsenal vs Chelsea",
                            sub="Arsenal", yes_ask=45.0)])
    assert out[0]["ask"] == pytest.approx(0.45)


def test_unparseable_rows_are_dropped_not_guessed():
    assert km.normalise([raw("KXEPLGAME-X", "KXEPLGAME", "some nonsense title")]) == []
    assert km.normalise([raw("KXEPLGAME-X", "KXEPLGAME", "Arsenal vs Chelsea", sub="???")]) == []


def test_unknown_team_is_dropped():
    assert km.normalise([raw("KXEPLGAME-X", "KXEPLGAME",
                             "Wednesfield FC vs Chelsea", sub="Chelsea")]) == []


def test_closed_markets_skipped():
    assert km.normalise([raw("KXEPLGAME-X", "KXEPLGAME", "Arsenal vs Chelsea",
                             sub="Arsenal", status="closed")]) == []


def test_out_of_scope_series_ignored():
    assert km.normalise([raw("KXEPLCORNERS-X", "KXEPLCORNERS",
                             "Arsenal vs Chelsea", sub="Over 9.5")]) == []


# --- Fail-closed ------------------------------------------------------------

def test_stake_places_nothing_when_kalshi_unavailable(monkeypatch):
    from src.market.kalshi_client import KalshiUnavailable
    monkeypatch.setattr(matchweek, "collect_kalshi",
                        lambda: (_ for _ in ()).throw(KalshiUnavailable("down")))
    rep = matchweek.run_stake()
    assert not rep.ok and rep.errors
    assert all(a["bankroll"] == 10_000.0 for a in ledger.load_state()["arms"].values())


def test_stake_places_nothing_when_odds_unavailable(monkeypatch):
    from src.data.odds_api import OddsUnavailable
    monkeypatch.setattr(matchweek, "collect_kalshi",
                        lambda: [{"home": "arsenal", "away": "chelsea", "league": "epl",
                                  "market": MARKET_1X2, "selection": "home",
                                  "ask": 0.40, "kickoff": _soon()}])
    monkeypatch.setattr(matchweek, "collect_fair_values",
                        lambda: (_ for _ in ()).throw(OddsUnavailable("no odds")))
    rep = matchweek.run_stake()
    assert not rep.ok
    assert all(a["bankroll"] == 10_000.0 for a in ledger.load_state()["arms"].values())


def test_stake_aborts_when_no_markets_listed(monkeypatch):
    monkeypatch.setattr(matchweek, "collect_kalshi", lambda: [])
    rep = matchweek.run_stake()
    assert not rep.ok and "no in-scope markets" in rep.errors[0]


def test_dry_run_plans_without_placing(monkeypatch):
    # A dry run still walks the order book: showing what WOULD be bet is only
    # useful if the prices shown are ones we could actually have got.
    monkeypatch.setattr(matchweek, "fetch_orderbook",
                        lambda c, t: {"orderbook_fp": {"no_dollars": [["0.6000", "1000000.00"]]}})
    monkeypatch.setattr(matchweek, "collect_kalshi",
                        lambda: [{"home": "arsenal", "away": "chelsea", "league": "epl",
                                  "market": MARKET_1X2, "selection": "home",
                                  "ask": 0.40, "kickoff": _soon(), "ticker": "TKR"}])
    monkeypatch.setattr(matchweek, "collect_fair_values",
                        lambda: {("arsenal", "chelsea"): {MARKET_1X2: {"home": 0.55}}})
    monkeypatch.setattr(matchweek, "collect_model_probs", lambda fx: {})
    rep = matchweek.run_stake(dry_run=True)
    assert rep.ok and rep.details["planned"]["A_divergence_kelly"] == 1
    assert all(a["bankroll"] == 10_000.0 for a in ledger.load_state()["arms"].values())


def test_report_is_written_to_disk(monkeypatch):
    monkeypatch.setattr(matchweek, "collect_kalshi", lambda: [])
    matchweek.run_stake()
    assert list((matchweek.LOG_DIR).glob("*_stake.json"))


# --- Settle -----------------------------------------------------------------

def test_settle_records_results_and_voids():
    from src.market.grading import Bet
    ledger.place_bet("A_divergence_kelly",
                     Bet(market=MARKET_1X2, selection="home", home="arsenal",
                         away="chelsea", stake=100.0, price=0.5))
    ledger.place_bet("B_divergence_flat",
                     Bet(market=MARKET_1X2, selection="home", home="everton",
                         away="fulham", stake=100.0, price=0.5))
    rep = matchweek.run_settle(
        results=[MatchResult("arsenal", "chelsea", 2, 0)],
        voids=[("everton", "fulham", "postponed")])
    assert rep.ok
    assert rep.details["settled"] == 1 and rep.details["voided"] == 1
    st = ledger.load_state()
    assert st["arms"]["B_divergence_flat"]["bankroll"] == 10_000.0     # refunded


def test_stake_records_edge_distribution_at_decision_time(monkeypatch, tmp_path):
    """
    The Friday run must record how far the market sat from the arms' bar.

    Arms A and B decline most weeks. Recording only that they planned nothing
    cannot distinguish "nowhere near the bar" from "missed it by a basis
    point", and that distinction is the entire evidence base for the season's
    A-versus-B conclusion. The snapshots sample near kickoff; this samples the
    moment the decision is actually made.
    """
    from src.market import ledger as _ledger
    from src.pipeline import matchweek as mw
    monkeypatch.setattr(_ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_ledger, "LEDGER_PATH", str(tmp_path / "l.json"))
    monkeypatch.setattr(mw, "LOG_DIR", tmp_path / "logs")

    monkeypatch.setattr(mw, "collect_kalshi", lambda: [
        {"home": "arsenal", "away": "chelsea", "market": "1x2", "selection": "home",
         "ask": 0.40, "league": "epl", "kickoff": _soon()},
    ])
    monkeypatch.setattr(mw, "collect_fair_values", lambda: {
        ("arsenal", "chelsea"): {"1x2": {"home": 0.55, "draw": 0.25, "away": 0.20}},
    })
    monkeypatch.setattr(mw, "collect_model_probs", lambda fx: {})

    report = mw.run_stake(dry_run=True)
    dist = report.details["edge_distribution"]
    assert dist["n"] >= 1
    assert "max" in dist and "median" in dist and "count_over" in dist


def test_stake_edge_distribution_costs_no_extra_odds_call(monkeypatch, tmp_path):
    """It must reuse the fair values already built, not fetch them again."""
    from src.market import ledger as _ledger
    from src.pipeline import matchweek as mw
    monkeypatch.setattr(_ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_ledger, "LEDGER_PATH", str(tmp_path / "l.json"))
    monkeypatch.setattr(mw, "LOG_DIR", tmp_path / "logs")

    calls = []
    monkeypatch.setattr(mw, "collect_kalshi", lambda: [
        {"home": "arsenal", "away": "chelsea", "market": "1x2", "selection": "home",
         "ask": 0.40, "league": "epl", "kickoff": _soon()},
    ])

    def _fair():
        calls.append(1)
        return {("arsenal", "chelsea"): {"1x2": {"home": 0.55, "draw": 0.25, "away": 0.20}}}

    monkeypatch.setattr(mw, "collect_fair_values", _fair)
    monkeypatch.setattr(mw, "collect_model_probs", lambda fx: {})

    mw.run_stake(dry_run=True)
    assert len(calls) == 1, f"collect_fair_values called {len(calls)}x; must be reused"


def test_snapshot_edge_distribution_excludes_in_play_markets(monkeypatch, tmp_path):
    """
    A goal scored after kickoff can blow a live Kalshi ask miles from the
    static pre-match fair value the model priced. That is not a missed edge,
    and it must not appear in the telemetry the season's A/B/D conclusion
    rests on.
    """
    from src.market import ledger as _ledger
    from src.pipeline import matchweek as mw
    monkeypatch.setattr(_ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_ledger, "LEDGER_PATH", str(tmp_path / "l.json"))
    monkeypatch.setattr(mw, "LOG_DIR", tmp_path / "logs")

    monkeypatch.setattr(mw, "collect_kalshi", lambda: [
        {"home": "arsenal", "away": "chelsea", "market": "1x2", "selection": "home",
         "ask": 0.90, "league": "epl", "kickoff": _soon(days=-1)},   # already started
        {"home": "wolves", "away": "everton", "market": "1x2", "selection": "home",
         "ask": 0.40, "league": "epl", "kickoff": _soon(days=2)},
    ])
    monkeypatch.setattr(mw, "collect_fair_values", lambda: {
        ("arsenal", "chelsea"): {"1x2": {"home": 0.20, "draw": 0.30, "away": 0.50}},
        ("wolves", "everton"): {"1x2": {"home": 0.55, "draw": 0.25, "away": 0.20}},
    })

    report = mw.run_snapshot()
    dist = report.details["edge_distribution"]
    assert dist["n"] == 1
