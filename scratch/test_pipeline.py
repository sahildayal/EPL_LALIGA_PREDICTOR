"""Pipeline tests: market parsing and the fail-closed guarantee."""
import pytest

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
        {"home": "arsenal", "away": "chelsea", "market": "1x2",
         "selection": "home", "ask": 0.40, "league": "epl"},
        {"home": "liverpool", "away": "everton", "market": "1x2",
         "selection": "home", "ask": 0.40, "league": "epl"},
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
