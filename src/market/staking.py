"""
Stake sizing for the four season arms.

Two defects in the old code motivate this module:

1. **A Kelly floor that defeated Kelly.** `max(0.02, min(0.15, 0.25 * f_star))`
   forced a 2% stake even on a 0.1% edge, and permitted 15% of bankroll on a
   single bet. Kelly's entire purpose is to stake *proportionally to edge*; a
   floor converts it into flat betting on whatever the model happened to like.

2. **No fee awareness.** Edge was computed as `model_prob - price` with no
   deduction, so bets that were negative EV after fees were sized as winners.

Kelly is also superlinearly sensitive to overstating p. The baseline board found
no model beating the market, so live edges come from Kalshi-vs-sharp divergence
and are small. Quarter-Kelly with a hard cap is the appropriate posture; full
Kelly on an uncertain p is how bankrolls die.
"""
from dataclasses import dataclass

from src.market.fees import fee_as_fraction_of_payout, net_expected_value

CONTRACTS_PER_UNIT = 100.0     # a "unit" of 100 contracts pays $100 on a win


@dataclass(frozen=True)
class StakePlan:
    stake: float
    contracts: float
    fraction: float
    kelly_full: float
    edge_net: float
    reason: str

    @property
    def should_bet(self) -> bool:
        return self.stake > 0.0


def kelly_fraction(fair_prob: float, price: float) -> float:
    """
    Full-Kelly fraction for a binary contract bought at `price`.

    Payoff is $1 per contract, so net odds b = (1 - price) / price and

        f* = (p * b - (1 - p)) / b = (p - price) / (1 - price)

    Negative means the bet is unfavourable; callers must not bet it.
    """
    if not 0.0 < price < 1.0:
        raise ValueError(f"price must be strictly between 0 and 1, got {price}")
    return (fair_prob - price) / (1.0 - price)


def quarter_kelly(fair_prob: float, price: float, bankroll: float,
                  cap: float = 0.03, min_edge: float = 0.02,
                  kelly_scale: float = 0.25) -> StakePlan:
    """
    Fee-aware fractional Kelly with a hard cap and NO floor.

    `min_edge` is a net-of-fee probability edge, defaulting to 2 points. Below it
    we do not bet at all — the old code's 2% minimum stake is deliberately absent,
    because a tiny edge deserves a tiny stake or none.
    """
    if bankroll <= 0:
        return StakePlan(0, 0, 0, 0, 0, "bankroll exhausted")

    fee_frac = fee_as_fraction_of_payout(price, CONTRACTS_PER_UNIT)
    edge_net = (fair_prob - price) - fee_frac

    if edge_net <= 0:
        return StakePlan(0, 0, 0, 0, edge_net, f"negative after fees ({edge_net:+.4f})")
    if edge_net < min_edge:
        return StakePlan(0, 0, 0, 0, edge_net,
                         f"edge {edge_net:.4f} below threshold {min_edge:.4f}")

    f_full = kelly_fraction(fair_prob - fee_frac, price)
    if f_full <= 0:
        return StakePlan(0, 0, 0, f_full, edge_net, "non-positive kelly")

    fraction = min(kelly_scale * f_full, cap)
    stake = round(min(fraction * bankroll, bankroll), 2)
    if stake <= 0:
        return StakePlan(0, 0, fraction, f_full, edge_net, "stake rounds to zero")

    return StakePlan(stake, round(stake / price, 2), fraction, f_full, edge_net, "ok")


def flat_stake(fair_prob: float, price: float, bankroll: float,
               starting_bankroll: float, fraction: float = 0.01,
               min_edge: float = 0.02) -> StakePlan:
    """
    Fixed fraction of the STARTING bankroll, for arm B.

    Sizing off the starting bankroll rather than the current one keeps the stake
    genuinely flat, so arm B isolates the staking rule instead of quietly
    compounding like arm A.
    """
    if bankroll <= 0:
        return StakePlan(0, 0, 0, 0, 0, "bankroll exhausted")

    fee_frac = fee_as_fraction_of_payout(price, CONTRACTS_PER_UNIT)
    edge_net = (fair_prob - price) - fee_frac
    if edge_net < min_edge:
        return StakePlan(0, 0, 0, 0, edge_net,
                         f"edge {edge_net:.4f} below threshold {min_edge:.4f}")

    stake = round(min(fraction * starting_bankroll, bankroll), 2)
    if stake <= 0:
        return StakePlan(0, 0, 0, 0, edge_net, "stake rounds to zero")
    return StakePlan(stake, round(stake / price, 2), fraction, 0.0, edge_net, "ok")


def expected_value(fair_prob: float, price: float, stake: float) -> float:
    """Net expected dollar profit for a given stake, after fees."""
    if stake <= 0:
        return 0.0
    return net_expected_value(fair_prob, price, stake / price)
