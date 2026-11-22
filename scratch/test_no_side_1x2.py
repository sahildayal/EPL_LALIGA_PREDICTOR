"""The NO side of each 1X2 contract (draw-or-away, etc.), priced from 2026-11-22."""
from src.market.edge import build_opportunities
from src.market.grading import Bet, MatchResult, grade, describe, is_no_side, MARKET_1X2
from src.market.parlay_arm import _selection_mask
from src.pipeline import kalshi_markets as km


def _bet(sel):
    return Bet(market=MARKET_1X2, selection=sel, home="arsenal", away="chelsea",
               stake=10.0, price=0.4)


def test_not_home_wins_on_draw_and_away_win_and_loses_on_home_win():
    assert grade(_bet("not_home"), MatchResult("arsenal", "chelsea", 1, 1))
    assert grade(_bet("not_home"), MatchResult("arsenal", "chelsea", 0, 2))
    assert not grade(_bet("not_home"), MatchResult("arsenal", "chelsea", 2, 0))
    assert not grade(_bet("not_draw"), MatchResult("arsenal", "chelsea", 1, 1))
    assert grade(_bet("not_away"), MatchResult("arsenal", "chelsea", 1, 1))


def test_label_and_side():
    assert describe(_bet("not_home")).endswith("Moneyline: NOT Arsenal Win")
    assert is_no_side("not_draw") and is_no_side("under") and not is_no_side("home")


def test_fair_value_is_the_complement_of_the_sharp_1x2():
    fair = {("arsenal", "chelsea"): {"1x2": {"home": 0.50, "draw": 0.27, "away": 0.23}}}
    mk = [{"home": "arsenal", "away": "chelsea", "market": "1x2",
           "selection": "not_home", "ask": 0.45}]
    [opp] = build_opportunities(mk, fair)
    assert abs(opp.fair_prob - 0.50) < 1e-12
    assert opp.gross_edge > 0


def test_model_priced_complement_for_arm_c():
    model = {("arsenal", "chelsea"): {"1x2": {"home": 0.6, "draw": 0.25, "away": 0.15}}}
    mk = [{"home": "arsenal", "away": "chelsea", "market": "1x2",
           "selection": "not_away", "ask": 0.80}]
    [opp] = build_opportunities(mk, {}, model, allow_model_priced=True)
    assert abs(opp.fair_prob - 0.85) < 1e-12 and abs(opp.model_prob - 0.85) < 1e-12


def test_normalise_emits_both_sides_of_a_1x2_contract(monkeypatch):
    monkeypatch.setattr(km, "parse_teams", lambda m: ("arsenal", "chelsea"))
    raw = [{"ticker": "KXEPLGAME-26NOV28ARSCHE-ARS", "series_ticker": "KXEPLGAME",
            "status": "active", "yes_sub_title": "Arsenal",
            "yes_ask_dollars": "0.52", "yes_bid_dollars": "0.50",
            "no_ask_dollars": "0.50", "no_bid_dollars": "0.48",
            "occurrence_datetime": "2026-11-28T18:00:00Z"}]
    rows = {r["selection"]: r for r in km.normalise(raw)}
    assert rows["home"]["ask"] == 0.52 and rows["home"]["bid"] == 0.50
    assert rows["not_home"]["ask"] == 0.50 and rows["not_home"]["bid"] == 0.48


def test_parlay_mask_for_not_home_is_draw_or_away():
    m = _selection_mask("1x2", "not_home", None, 4)
    assert m[1, 1] and m[0, 2] and not m[2, 0]
