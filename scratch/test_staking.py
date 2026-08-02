"""Fee and staking tests — the two places the old code lost money by construction."""
import pytest

from src.market.fees import (
    fee_per_contract, total_fee, fee_as_fraction_of_stake, net_expected_value,
)
from src.market.staking import kelly_fraction, quarter_kelly, flat_stake, expected_value


# --- Fees -------------------------------------------------------------------

def test_fee_peaks_at_fifty_cents():
    """The 0.07*p*(1-p) term is maximised at p=0.5."""
    assert fee_per_contract(0.50) >= fee_per_contract(0.25)
    assert fee_per_contract(0.50) >= fee_per_contract(0.90)


@pytest.mark.parametrize("contracts,price,expected", [
    # Kalshi's published schedule. The 100-lot case is the one that caught a
    # units bug: fee is $1.75, not $0.02.
    (1, 0.50, 0.02),
    (1, 0.30, 0.02),
    (1, 0.90, 0.01),
    (1, 0.10, 0.01),
    (100, 0.50, 1.75),
])
def test_fee_matches_published_schedule(contracts, price, expected):
    assert total_fee(price, contracts) == pytest.approx(expected, abs=0.005)


def test_fee_scales_with_order_size():
    """A 100-lot must cost about 100x a single contract, not the same."""
    assert total_fee(0.50, 100) > total_fee(0.50, 1) * 50


def test_minimum_fee_applies():
    assert fee_per_contract(0.99) == pytest.approx(0.01)
    assert fee_per_contract(0.01) == pytest.approx(0.01)


def test_longshots_are_proportionally_more_expensive():
    """
    Two regimes, and the difference matters for arm D.

    Small orders: the 1c minimum dominates, so a single 3c contract pays a 33%
    tax versus 4% at even money — an 8x penalty.
    At scale the minimum stops binding and the gap narrows to about 2x.
    """
    # single contract: minimum fee dominates
    assert fee_as_fraction_of_stake(0.03, 1) == pytest.approx(1 / 3, abs=0.02)
    assert fee_as_fraction_of_stake(0.03, 1) > fee_as_fraction_of_stake(0.50, 1) * 5

    # 100-lot: minimum no longer binds, longshot still ~2x costlier
    big_long = fee_as_fraction_of_stake(0.03, 100)
    big_even = fee_as_fraction_of_stake(0.50, 100)
    assert 1.5 < big_long / big_even < 3.0


def test_fee_on_fifty_cent_market_is_material():
    """3.5% of stake at even money is why 'edge > 0' was never good enough."""
    assert fee_as_fraction_of_stake(0.50, 100) == pytest.approx(0.035, abs=0.002)


def test_invalid_prices_rejected():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            fee_per_contract(bad)


def test_net_ev_negative_when_edge_only_covers_fees():
    # 1 point of edge at 50c does not cover the fee
    assert net_expected_value(0.51, 0.50, 100) < 0
    assert net_expected_value(0.60, 0.50, 100) > 0


# --- Kelly ------------------------------------------------------------------

def test_kelly_zero_at_fair_price():
    assert kelly_fraction(0.50, 0.50) == pytest.approx(0.0)


def test_kelly_negative_when_overpriced():
    assert kelly_fraction(0.45, 0.50) < 0


def test_kelly_grows_with_edge():
    assert kelly_fraction(0.70, 0.50) > kelly_fraction(0.60, 0.50) > kelly_fraction(0.55, 0.50)


def test_kelly_formula_is_correct():
    # f* = (p - price) / (1 - price)
    assert kelly_fraction(0.60, 0.50) == pytest.approx(0.2)


# --- Quarter-Kelly staking ---------------------------------------------------

def test_no_bet_when_edge_is_negative_after_fees():
    plan = quarter_kelly(0.505, 0.50, 10_000)
    assert not plan.should_bet and plan.stake == 0


def test_no_floor_tiny_edge_gets_no_bet():
    """
    The old code forced 2% of bankroll ($200) on a 0.1% edge. That is the bug
    this test exists to prevent regressing.
    """
    plan = quarter_kelly(0.5015, 0.50, 10_000)
    assert plan.stake == 0.0
    assert "below threshold" in plan.reason or "negative" in plan.reason


def test_real_edge_gets_a_proportional_stake():
    plan = quarter_kelly(0.60, 0.50, 10_000)
    assert plan.should_bet
    assert 0 < plan.fraction <= 0.03
    assert plan.stake == pytest.approx(plan.fraction * 10_000, abs=0.01)


def test_stake_scales_with_edge():
    small = quarter_kelly(0.56, 0.50, 10_000)
    big = quarter_kelly(0.75, 0.50, 10_000)
    assert big.stake >= small.stake


def test_hard_cap_is_respected_even_on_huge_edge():
    plan = quarter_kelly(0.99, 0.50, 10_000, cap=0.03)
    assert plan.fraction <= 0.03
    assert plan.stake <= 300.0


def test_never_stakes_more_than_bankroll():
    plan = quarter_kelly(0.95, 0.20, 50.0)
    assert plan.stake <= 50.0


def test_exhausted_bankroll_cannot_bet():
    assert quarter_kelly(0.90, 0.50, 0.0).stake == 0.0


def test_contracts_consistent_with_stake_and_price():
    plan = quarter_kelly(0.65, 0.40, 10_000)
    assert plan.contracts == pytest.approx(plan.stake / 0.40, abs=0.01)


# --- Flat staking (arm B) ----------------------------------------------------

def test_flat_stake_is_constant_regardless_of_edge():
    a = flat_stake(0.60, 0.50, 9_000, 10_000)
    b = flat_stake(0.80, 0.50, 9_000, 10_000)
    assert a.stake == b.stake == 100.0


def test_flat_stake_uses_starting_bankroll_not_current():
    """Otherwise arm B compounds and stops isolating the staking rule."""
    down = flat_stake(0.60, 0.50, 5_000, 10_000)
    assert down.stake == 100.0


def test_flat_stake_still_respects_the_edge_threshold():
    assert flat_stake(0.505, 0.50, 10_000, 10_000).stake == 0.0


def test_flat_stake_capped_by_remaining_bankroll():
    assert flat_stake(0.60, 0.50, 40.0, 10_000).stake == 40.0


# --- EV ---------------------------------------------------------------------

def test_expected_value_positive_on_real_edge():
    assert expected_value(0.60, 0.50, 100.0) > 0


def test_expected_value_zero_for_no_stake():
    assert expected_value(0.60, 0.50, 0.0) == 0.0
