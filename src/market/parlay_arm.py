"""
Arm D: multi-leg wagers, priced honestly enough to be worth losing money on.

A parlay is not a bet with a bigger edge; it is a bet with a compounded edge and
a compounded error. Three things make it structurally harder than a single, and
each one is handled explicitly here rather than assumed away:

1. **Fees compound per leg.** Kalshi charges the fee on each contract, so a
   three-leg parlay pays three fees against one payout. This is the single
   biggest reason parlays lose, and it is why arm D carries the widest
   threshold of the four arms.

2. **Correlation.** Multiplying leg probabilities is only valid when the legs
   are independent. For legs in DIFFERENT fixtures that is close enough to true.
   For legs in the SAME fixture it is badly wrong — "home win" and "over 2.5"
   are positively correlated, and multiplying understates the joint probability.
   Same-game legs are therefore priced off the fitted Dixon-Coles score matrix
   that already anchors our BTTS derivation, which gives the exact joint
   probability under that distribution instead of an independence fiction.

3. **The winner's curse.** Enumerating every combination and keeping the best
   one selects for estimation error as much as for edge, and the selection bias
   compounds multiplicatively across legs. Each leg's fair probability is
   therefore shrunk toward its ask before compounding — see LEG_SHRINKAGE.

**Documented assumption.** We price the combined ask as the product of the leg
asks. Kalshi's own multi-leg quote would be no better than that and is usually
worse, so this assumption flatters arm D. It is recorded on every parlay as
`ask_is_synthetic` so the season result can be read with it in mind, and
same-game parlays carry an extra penalty because a real book prices the
correlation into the ask and we cannot observe that price.
"""
from dataclasses import dataclass, field, asdict
from itertools import combinations
from typing import Optional

from src.market.edge import CONTRACTS_PER_UNIT
from src.market.fees import total_fee
from src.market.grading import Bet, MARKET_1X2, MARKET_TOTALS, MARKET_BTTS

MIN_LEGS = 2
MAX_LEGS = 3

# Each leg's fair probability is pulled this fraction of the way toward its ask
# before the legs are compounded.
#
# The justification is maximum-selection bias. We enumerate every eligible
# combination and keep the best few, so the winners are disproportionately the
# ones whose fair estimate happens to be biased high. On a single bet that bias
# costs you once; on a three-leg parlay the three biases multiply, and a 2% overstatement
# per leg becomes ~6% on the product. Shrinking toward the ask is the cheapest
# available correction: it costs nothing when the estimate is right and removes
# most of the compounding when it is not.
LEG_SHRINKAGE = 0.15

# Extra edge demanded of a same-game parlay, on top of the arm threshold.
#
# Our joint probability for same-game legs comes from the score matrix fitted to
# the sharp 1X2 and totals. That fit reproduces those prices but is not itself a
# sharp quote of the joint market, and a real book would price the correlation
# into its ask. We cannot see that price, so we charge ourselves for not seeing it.
SGP_PENALTY = 0.02

# The combined ask is assumed, not observed. Charge for that too.
SYNTHETIC_ASK_PENALTY = 0.01


@dataclass
class ParlayLeg:
    """One leg. Mirrors an Opportunity but carries only what settlement needs."""
    home: str
    away: str
    market: str
    selection: str
    fair_prob: float
    ask: float
    line: Optional[float] = None
    league: Optional[str] = None
    kickoff: Optional[str] = None
    ticker: Optional[str] = None
    result: Optional[str] = None            # WIN|LOSS, set leg-by-leg at settlement

    @property
    def fixture(self) -> tuple:
        return (self.home, self.away)

    def to_bet(self) -> Bet:
        """A zero-stake Bet, purely so the existing grader can grade this leg."""
        return Bet(market=self.market, selection=self.selection,
                   home=self.home, away=self.away, stake=0.0, price=self.ask,
                   line=self.line, league=self.league, kickoff=self.kickoff,
                   fair_prob=self.fair_prob)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ParlayLeg":
        known = {f for f in ParlayLeg.__dataclass_fields__}
        return ParlayLeg(**{k: v for k, v in d.items() if k in known})


@dataclass
class Parlay:
    """A multi-leg wager. Stake is charged once; fees are charged per leg."""
    legs: list
    stake: float = 0.0
    fair_prob: float = 0.0                  # joint, after shrinkage
    ask: float = 0.0                        # product of leg asks (synthetic)
    net_edge: float = 0.0
    is_sgp: bool = False
    ask_is_synthetic: bool = True
    joint_method: str = ""                  # 'independent' | 'score_matrix'
    label: str = ""
    placed_utc: Optional[str] = None
    result: Optional[str] = None            # WIN|LOSS
    payout: Optional[float] = None
    pnl: Optional[float] = None
    settled_utc: Optional[str] = None
    notes: list = field(default_factory=list)

    def __post_init__(self):
        if not MIN_LEGS <= len(self.legs) <= MAX_LEGS:
            raise ValueError(f"parlay needs {MIN_LEGS}-{MAX_LEGS} legs, got {len(self.legs)}")
        self.legs = [ParlayLeg.from_dict(l) if isinstance(l, dict) else l
                     for l in self.legs]
        if not self.label:
            self.label = describe(self)

    @property
    def decimal_odds(self) -> float:
        return 1.0 / max(self.ask, 1e-9)

    @property
    def fixtures(self) -> set:
        return {l.fixture for l in self.legs}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["legs"] = [l.to_dict() if not isinstance(l, dict) else l for l in self.legs]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Parlay":
        known = {f for f in Parlay.__dataclass_fields__}
        return Parlay(**{k: v for k, v in d.items() if k in known})


def describe(parlay: "Parlay") -> str:
    """Display only. Never parsed back — that bug is not being reintroduced."""
    parts = []
    for l in parlay.legs:
        h, a = l.home.title(), l.away.title()
        if l.market == MARKET_1X2:
            pick = {"home": h, "draw": "Draw", "away": a}[l.selection]
            parts.append(f"{h}/{a}: {pick}")
        elif l.market == MARKET_TOTALS:
            parts.append(f"{h}/{a}: {l.selection.title()} {l.line}")
        elif l.market == MARKET_BTTS:
            parts.append(f"{h}/{a}: BTTS {l.selection.upper()}")
        else:
            parts.append(f"{h}/{a}: {l.market} {l.selection}")
    kind = "SGP" if parlay.is_sgp else f"{len(parlay.legs)}-leg parlay"
    return f"{kind} — " + " + ".join(parts)


# --- Joint probability -------------------------------------------------------

def _shrunk(fair: float, ask: float) -> float:
    """Pulls a leg's fair probability toward its ask. See LEG_SHRINKAGE."""
    return fair - LEG_SHRINKAGE * (fair - ask)


def _selection_mask(market: str, selection: str, line, n: int):
    """Boolean scoreline-matrix mask for one leg. None when unsupported."""
    import numpy as np
    totals = np.add.outer(np.arange(n), np.arange(n))
    idx_h, idx_a = np.indices((n, n))

    if market == MARKET_1X2:
        if selection == "home":
            return idx_h > idx_a
        if selection == "away":
            return idx_a > idx_h
        if selection == "draw":
            return idx_h == idx_a
        return None
    if market == MARKET_TOTALS:
        if line is None:
            return None
        if selection == "over":
            return totals > line
        if selection == "under":
            return totals < line
        return None
    if market == MARKET_BTTS:
        both = (idx_h >= 1) & (idx_a >= 1)
        if selection == "yes":
            return both
        if selection == "no":
            return ~both
        return None
    return None


def joint_from_score_matrix(legs: list, matrix) -> Optional[float]:
    """
    Exact joint probability of same-fixture legs under a scoreline distribution.

    Returns None when any leg cannot be expressed as a region of the matrix, in
    which case the caller must NOT fall back to multiplying — an independence
    assumption applied to same-game legs is precisely the error this exists to
    avoid. Not pricing the parlay is the correct outcome.

    Integer totals lines are renormalised over the no-push region, matching the
    convention used everywhere else that a de-vigged over/under pair sums to 1.
    """
    import numpy as np
    n = matrix.shape[0]
    mask = np.ones((n, n), dtype=bool)
    live = np.ones((n, n), dtype=bool)
    totals = np.add.outer(np.arange(n), np.arange(n))

    for leg in legs:
        m = _selection_mask(leg.market, leg.selection, leg.line, n)
        if m is None:
            return None
        mask &= m
        if leg.market == MARKET_TOTALS and leg.line is not None and float(leg.line).is_integer():
            live &= totals != int(leg.line)

    denom = float(matrix[live].sum())
    if denom <= 0:
        return None
    return float(matrix[mask & live].sum()) / denom


def price_parlay(legs: list, score_matrices: dict = None) -> Optional[dict]:
    """
    Prices one combination, or returns None if it cannot be priced honestly.

    `score_matrices` maps (home, away) -> fitted scoreline matrix, and is
    REQUIRED for any combination with two legs in the same fixture.
    """
    score_matrices = score_matrices or {}
    if not MIN_LEGS <= len(legs) <= MAX_LEGS:
        return None

    # Never stake two legs of the same market on the same fixture: they are
    # either mutually exclusive (home + away) or one implies the other.
    seen = set()
    for l in legs:
        key = (l.fixture, l.market)
        if key in seen:
            return None
        seen.add(key)

    fixtures = [l.fixture for l in legs]
    is_sgp = len(set(fixtures)) < len(fixtures)

    ask = 1.0
    for l in legs:
        ask *= l.ask
    if not 0.0 < ask < 1.0:
        return None

    if is_sgp:
        # Every same-fixture group must be priced off that fixture's matrix.
        groups, joint, method = {}, 1.0, "score_matrix"
        for l in legs:
            groups.setdefault(l.fixture, []).append(l)
        for fixture, group in groups.items():
            if len(group) == 1:
                joint *= _shrunk(group[0].fair_prob, group[0].ask)
                continue
            matrix = score_matrices.get(fixture)
            if matrix is None:
                return None
            exact = joint_from_score_matrix(group, matrix)
            if exact is None:
                return None
            # Shrink the joint estimate once, using the group's product of asks
            # as the reference. Shrinking each leg first then combining would
            # apply the correction len(group) times over.
            group_ask = 1.0
            for l in group:
                group_ask *= l.ask
            joint *= _shrunk(exact, group_ask)
    else:
        joint, method = 1.0, "independent"
        for l in legs:
            joint *= _shrunk(l.fair_prob, l.ask)

    # Fees are charged per leg against a single payout. This is the arithmetic
    # that makes parlays hard, so it is computed explicitly rather than folded
    # into a rate.
    contracts = CONTRACTS_PER_UNIT
    payout = contracts                                   # $1 per winning contract
    fees = sum(total_fee(l.ask, contracts) for l in legs)
    fee_frac = fees / payout if payout > 0 else 1.0

    penalty = SYNTHETIC_ASK_PENALTY + (SGP_PENALTY if is_sgp else 0.0)
    net_edge = joint - ask - fee_frac - penalty

    return {
        "legs": legs,
        "fair_prob": joint,
        "ask": ask,
        "fee_frac": fee_frac,
        "penalty": penalty,
        "net_edge": net_edge,
        "is_sgp": is_sgp,
        "joint_method": method,
    }


# --- Selection ---------------------------------------------------------------

def legs_from_opportunities(opportunities: list) -> list:
    """Converts priced singles into parlay legs, dropping unsupported markets."""
    out = []
    for o in opportunities:
        if o.market not in (MARKET_1X2, MARKET_TOTALS, MARKET_BTTS):
            continue
        out.append(ParlayLeg(
            home=o.home, away=o.away, market=o.market, selection=o.selection,
            fair_prob=o.fair_prob, ask=o.ask, line=o.line,
            league=o.league, kickoff=o.kickoff, ticker=o.ticker,
        ))
    return out


def enumerate_parlays(legs: list, score_matrices: dict = None,
                      min_edge: float = 0.05, max_candidates: int = 400,
                      min_ask: float = 0.05) -> list:
    """
    All priceable combinations clearing `min_edge`, best net edge first.

    `max_candidates` bounds the enumeration. Combination counts grow as C(n,3),
    so 40 legs is already 9,880 candidates — and the more combinations we look
    at, the more the best one is selected on error rather than edge. The cap is
    a real defence, not just a performance guard.
    """
    legs = sorted(legs, key=lambda l: l.fair_prob - l.ask, reverse=True)[:24]
    priced, examined = [], 0

    for size in range(MIN_LEGS, MAX_LEGS + 1):
        for combo in combinations(legs, size):
            examined += 1
            if examined > max_candidates:
                break
            p = price_parlay(list(combo), score_matrices)
            if p is None or p["net_edge"] < min_edge:
                continue
            # A combined ask this thin is a lottery ticket whose edge estimate
            # is dominated by the tails of three separate models.
            if p["ask"] < min_ask:
                continue
            priced.append(p)
        if examined > max_candidates:
            break

    return sorted(priced, key=lambda p: p["net_edge"], reverse=True)


def select_parlays(priced: list, max_parlays: int = 3) -> list:
    """
    Keeps a few non-overlapping parlays.

    Two parlays sharing a leg are not two bets; they are one bet with extra
    steps, and sizing them independently understates the true exposure to that
    leg. Overlap is therefore forbidden outright rather than discounted.
    """
    chosen, used = [], set()
    for p in priced:
        keys = {(l.fixture, l.market, l.selection) for l in p["legs"]}
        if keys & used:
            continue
        chosen.append(p)
        used |= keys
        if len(chosen) >= max_parlays:
            break
    return chosen
