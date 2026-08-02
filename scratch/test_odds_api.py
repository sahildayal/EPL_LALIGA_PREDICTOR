"""De-vigging tests. These probabilities are the anchor of every bet we place."""
import pytest

from src.data.odds_api import (
    devig, devig_shin, devig_multiplicative, _consensus_odds, OddsUnavailable,
)

# Real Pinnacle line, Arsenal vs Coventry, 2026-08-21 (booksum ~1.05)
ARS_COV = {"Arsenal": 1.16, "Coventry City": 16.01, "Draw": 8.01}
EVENISH = {"Home": 2.60, "Draw": 3.40, "Away": 2.90}


@pytest.mark.parametrize("method", ["shin", "multiplicative"])
@pytest.mark.parametrize("odds", [ARS_COV, EVENISH])
def test_probabilities_sum_to_one(method, odds):
    p = devig(odds, method=method)
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert all(0.0 < v < 1.0 for v in p.values())


def test_devig_strips_the_margin():
    raw_booksum = sum(1 / o for o in ARS_COV.values())
    assert raw_booksum > 1.0                      # there is a margin to strip
    assert abs(sum(devig(ARS_COV).values()) - 1.0) < 1e-9


def test_devigged_probs_are_below_raw_implied():
    """Every outcome's fair probability must be below its vigged implied probability."""
    fair = devig(ARS_COV)
    for k, o in ARS_COV.items():
        assert fair[k] < 1.0 / o


def test_shin_shades_favourite_up_relative_to_proportional():
    """
    The favourite-longshot correction: Shin should assign the heavy favourite a
    HIGHER fair probability than proportional de-vigging, and the longshot a
    lower one. This is the whole reason we prefer it.
    """
    shin = devig_shin(ARS_COV)
    prop = devig_multiplicative(ARS_COV)
    assert shin["Arsenal"] > prop["Arsenal"]
    assert shin["Coventry City"] < prop["Coventry City"]


def test_shin_and_proportional_agree_on_a_balanced_book():
    """With little favourite-longshot skew the two methods should nearly coincide."""
    shin, prop = devig_shin(EVENISH), devig_multiplicative(EVENISH)
    for k in EVENISH:
        assert abs(shin[k] - prop[k]) < 0.02


def test_two_way_market_falls_back_to_proportional():
    two = {"Yes": 1.80, "No": 2.10}
    assert devig_shin(two) == devig_multiplicative(two)
    assert abs(sum(devig_shin(two).values()) - 1.0) < 1e-9


def test_arbitrage_book_is_handled_not_crashed():
    arb = {"Home": 2.20, "Away": 2.20}          # booksum < 1
    p = devig(arb)
    assert abs(sum(p.values()) - 1.0) < 1e-9


def test_insufficient_prices_raise():
    with pytest.raises(OddsUnavailable):
        devig({"Home": 1.9})
    with pytest.raises(OddsUnavailable):
        devig({"Home": 0.0, "Away": 1.0})       # 1.0 and below are invalid decimal odds


def test_unknown_method_rejected():
    with pytest.raises(ValueError):
        devig(ARS_COV, method="magic")


# --- Bookmaker selection ----------------------------------------------------

def _book(key, prices):
    return {"key": key, "markets": [{"key": "h2h",
            "outcomes": [{"name": n, "price": p} for n, p in prices.items()]}]}


def test_pinnacle_is_preferred_over_other_books():
    books = [_book("betvictor", {"Home": 2.0, "Away": 2.0}),
             _book("pinnacle", {"Home": 1.5, "Away": 2.7})]
    odds, source = _consensus_odds(books, "h2h")
    assert source == "pinnacle" and odds["Home"] == 1.5


def test_median_consensus_when_no_sharp_book():
    books = [_book("a", {"Home": 2.0, "Away": 4.0}),
             _book("b", {"Home": 2.2, "Away": 4.2}),
             _book("c", {"Home": 9.9, "Away": 4.4})]      # 9.9 is a stale outlier
    odds, source = _consensus_odds(books, "h2h")
    assert source.startswith("consensus_median")
    assert odds["Home"] == 2.2                             # median ignores the outlier


def test_missing_market_raises():
    with pytest.raises(OddsUnavailable):
        _consensus_odds([_book("a", {"Home": 2.0, "Away": 2.0})], "totals")


def test_totals_outcomes_are_labelled_with_their_line():
    books = [{"key": "pinnacle", "markets": [{"key": "totals", "outcomes": [
        {"name": "Over", "price": 1.9, "point": 2.5},
        {"name": "Under", "price": 1.95, "point": 2.5}]}]}]
    odds, _ = _consensus_odds(books, "totals")
    assert set(odds) == {"Over 2.5", "Under 2.5"}
