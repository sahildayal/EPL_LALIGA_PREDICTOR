"""Pipeline tests: market parsing and the fail-closed guarantee."""
import pytest

from src.market import ledger
from src.market.grading import MARKET_1X2, MARKET_TOTALS, MARKET_BTTS, MatchResult
from src.pipeline import kalshi_markets as km
from src.pipeline import matchweek


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
                                  "market": MARKET_1X2, "selection": "home", "ask": 0.40}])
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
    monkeypatch.setattr(matchweek, "collect_kalshi",
                        lambda: [{"home": "arsenal", "away": "chelsea", "league": "epl",
                                  "market": MARKET_1X2, "selection": "home", "ask": 0.40}])
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
