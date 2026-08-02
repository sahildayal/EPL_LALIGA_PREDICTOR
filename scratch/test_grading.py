"""Grading tests, including regressions for the two bugs this module replaces."""
import pytest

from src.market.grading import (
    Bet, MatchResult, grade, UngradeableBet,
    MARKET_1X2, MARKET_TOTALS, MARKET_BTTS, MARKET_CORNERS, MARKET_ADVANCE, MARKET_PLAYER_PROP,
)


def mk(market, selection, **kw):
    kw.setdefault("home", "liverpool")
    kw.setdefault("away", "arsenal")
    kw.setdefault("stake", 100.0)
    kw.setdefault("price", 0.5)
    return Bet(market=market, selection=selection, **kw)


def res(hg, ag, **kw):
    return MatchResult(home="liverpool", away="arsenal", home_goals=hg, away_goals=ag, **kw)


# --- 1X2 -------------------------------------------------------------------

@pytest.mark.parametrize("sel,hg,ag,expected", [
    ("home", 2, 1, True), ("home", 1, 2, False), ("home", 1, 1, False),
    ("away", 1, 2, True), ("away", 2, 1, False), ("away", 1, 1, False),
    ("draw", 1, 1, True), ("draw", 2, 1, False),
])
def test_1x2(sel, hg, ag, expected):
    assert grade(mk(MARKET_1X2, sel), res(hg, ag)) is expected


def test_swapped_team_order_still_grades_correctly():
    bet = mk(MARKET_1X2, "home")                      # backing Liverpool
    swapped = MatchResult(home="arsenal", away="liverpool", home_goals=0, away_goals=3)
    assert grade(bet, swapped) is True                # Liverpool won 3-0


def test_unrelated_result_is_ungradeable():
    with pytest.raises(UngradeableBet):
        grade(mk(MARKET_1X2, "home"), MatchResult("chelsea", "everton", 1, 0))


# --- Totals ----------------------------------------------------------------

@pytest.mark.parametrize("sel,line,hg,ag,expected", [
    ("over", 2.5, 2, 1, True), ("over", 2.5, 1, 1, False),
    ("under", 2.5, 1, 1, True), ("under", 2.5, 3, 0, False),
    ("over", 1.5, 1, 1, True), ("over", 3.5, 2, 2, True),
    ("under", 4.5, 2, 2, True),
])
def test_totals_any_line(sel, line, hg, ag, expected):
    """The old grader only handled over 1.5 and over 2.5; everything else lost."""
    assert grade(mk(MARKET_TOTALS, sel, line=line), res(hg, ag)) is expected


def test_integer_line_push_is_ungradeable():
    with pytest.raises(UngradeableBet, match="push"):
        grade(mk(MARKET_TOTALS, "over", line=3.0), res(2, 1))


# --- BTTS ------------------------------------------------------------------

@pytest.mark.parametrize("sel,hg,ag,expected", [
    ("yes", 1, 1, True), ("yes", 2, 0, False),
    ("no", 2, 0, True), ("no", 1, 1, False),
])
def test_btts(sel, hg, ag, expected):
    assert grade(mk(MARKET_BTTS, sel), res(hg, ag)) is expected


# --- Regression: the "Darwin" substring bug --------------------------------

def test_player_named_darwin_is_not_graded_as_a_home_win():
    """
    Old grader: `"win" in bet_type` matched "Dar-win-", then `home in bet_type`
    matched because the label reads "... in Liverpool vs Arsenal". So a Darwin
    Nunez scorer prop was graded purely on whether Liverpool won.
    """
    bet = mk(MARKET_PLAYER_PROP, "darwin nunez", prop="goals_1")
    # Liverpool win 3-0, but Darwin did not score.
    r = res(3, 0, player_goals={"mohamed salah": 2, "cody gakpo": 1},
            player_assists={}, lineups_confirmed=True)
    assert grade(bet, r) is False       # old code returned True

    r2 = res(0, 1, player_goals={"darwin nunez": 1}, lineups_confirmed=True)
    assert grade(bet, r2) is True       # scored despite Liverpool losing


def test_harry_winks_same_bug():
    bet = mk(MARKET_PLAYER_PROP, "harry winks", prop="goals_1")
    r = res(2, 0, player_goals={"mohamed salah": 2}, lineups_confirmed=True)
    assert grade(bet, r) is False


def test_player_substring_does_not_false_positive():
    """'salah' must not match 'mohamed salah ali' or vice versa."""
    bet = mk(MARKET_PLAYER_PROP, "salah", prop="goals_1")
    r = res(1, 0, player_goals={"mohamed salah": 1}, lineups_confirmed=True)
    assert grade(bet, r) is False


# --- Regression: silent-loss markets ---------------------------------------

def test_corners_without_data_raises_not_loses():
    """Old grader returned False (LOSS) for every corners leg."""
    with pytest.raises(UngradeableBet):
        grade(mk(MARKET_CORNERS, "over", line=9.5), res(1, 0))


def test_corners_with_data_grades():
    assert grade(mk(MARKET_CORNERS, "over", line=9.5), res(1, 0, corners=11)) is True
    assert grade(mk(MARKET_CORNERS, "under", line=9.5), res(1, 0, corners=11)) is False


def test_advance_without_data_raises_not_loses():
    with pytest.raises(UngradeableBet):
        grade(mk(MARKET_ADVANCE, "home"), res(1, 0))


def test_advance_with_data_grades():
    assert grade(mk(MARKET_ADVANCE, "home"), res(1, 0, advanced="home")) is True
    assert grade(mk(MARKET_ADVANCE, "home"), res(1, 0, advanced="away")) is False


def test_player_prop_without_stats_raises_not_loses():
    bet = mk(MARKET_PLAYER_PROP, "darwin nunez", prop="goals_1")
    with pytest.raises(UngradeableBet):
        grade(bet, res(1, 0, lineups_confirmed=False))


# --- Schema ----------------------------------------------------------------

def test_unknown_market_rejected_at_construction():
    with pytest.raises(ValueError):
        Bet(market="handicap", selection="home", home="a", away="b", stake=1, price=0.5)


def test_totals_requires_a_line():
    with pytest.raises(ValueError):
        Bet(market=MARKET_TOTALS, selection="over", home="a", away="b", stake=1, price=0.5)


def test_roundtrip_and_odds():
    b = mk(MARKET_TOTALS, "over", line=2.5, price=0.4)
    assert abs(b.decimal_odds - 2.5) < 1e-9
    assert Bet.from_dict(b.to_dict()).label == b.label


def test_label_is_generated_but_never_parsed():
    b = mk(MARKET_1X2, "home")
    assert "Liverpool" in b.label and "Moneyline" in b.label
    b.label = "total nonsense"
    assert grade(b, res(2, 1)) is True
