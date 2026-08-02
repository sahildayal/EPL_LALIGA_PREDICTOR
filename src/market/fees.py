"""
Kalshi fee model.

The old pipeline modelled fees nowhere and accepted any bet with `edge > 0.0`.
On a market priced near 50c the fee is roughly 3.5% of capital deployed, so the
large majority of those "positive edge" bets were negative EV before a ball was
kicked. Parlays compounded it once per leg.

Kalshi's published trading fee, in DOLLARS, for C contracts at price P:

    fee = roundup_to_cent(0.07 * C * P * (1 - P))

Worked examples that pin the units down (both from Kalshi's published schedule):

    1 contract  @ $0.50 -> 0.07 * 1 * 0.25   = $0.0175 -> $0.02
    1 contract  @ $0.90 -> 0.07 * 1 * 0.09   = $0.0063 -> $0.01
    100 contracts @ $0.50 -> 0.07 * 100 * 0.25 = $1.75   -> $1.75  (3.5% of $50)

The quadratic term peaks at P = 0.50 and falls toward the extremes, but in
*proportional* terms longshots are the most expensive: the 1c minimum on a 3c
contract is a 33% tax, versus 3.5% at even money.
"""
import math

FEE_RATE = 0.07
MIN_FEE_DOLLARS = 0.01


def _roundup_cent(dollars: float) -> float:
    return math.ceil(dollars * 100.0 - 1e-9) / 100.0


def _validate(price: float):
    if not 0.0 < price < 1.0:
        raise ValueError(f"price must be strictly between 0 and 1, got {price}")


def total_fee(price: float, contracts: float) -> float:
    """Fee in dollars for `contracts` at `price`."""
    _validate(price)
    if contracts <= 0:
        return 0.0
    raw = FEE_RATE * contracts * price * (1.0 - price)
    return max(_roundup_cent(raw), MIN_FEE_DOLLARS)


def fee_per_contract(price: float) -> float:
    """Fee in dollars for a single contract."""
    return total_fee(price, 1.0)


def fee_as_fraction_of_stake(price: float, contracts: float = 100.0) -> float:
    """
    Fee as a fraction of capital deployed — the number that decides whether an
    edge survives contact with the exchange.
    """
    _validate(price)
    stake = price * contracts
    if stake <= 0:
        return 0.0
    return total_fee(price, contracts) / stake


def fee_as_fraction_of_payout(price: float, contracts: float = 100.0) -> float:
    """
    Fee per dollar of contract face value.

    This is the form to subtract from a probability edge, since a contract pays
    $1 and the edge is measured in probability units.
    """
    _validate(price)
    if contracts <= 0:
        return 0.0
    return total_fee(price, contracts) / contracts


def breakeven_edge(price: float, contracts: float = 100.0) -> float:
    """Minimum probability edge needed just to cover fees at this price."""
    return fee_as_fraction_of_payout(price, contracts)


def net_expected_value(fair_prob: float, price: float, contracts: float = 100.0) -> float:
    """
    Expected dollar profit from buying `contracts` YES at `price`, after fees.
    Each contract pays $1 on a win, $0 otherwise.
    """
    _validate(price)
    gross = (fair_prob - price) * contracts
    return gross - total_fee(price, contracts)
