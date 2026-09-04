"""
Divergence pricing: where does Kalshi disagree with the sharp line?

This is the whole strategy in one module. The evidence behind it, from
walk-forward CV over 16 seasons in two leagues:

  - No standalone model beat the market in any of 32 fold-league combinations.
  - Blending a model into the market converged to ZERO model weight when the
    weight was fitted walk-forward.

So fair value is the de-vigged sharp consensus, not our model. The model exists
only to price markets where no sharp line is posted, and its output is flagged
as such so the staking rule can treat it more cautiously.

An opportunity requires all of:
  1. a fair-value estimate,
  2. a Kalshi ask,
  3. edge = fair - ask - fee, above a minimum threshold.
"""
from dataclasses import dataclass, field
from typing import Optional

from src.data.canonical_teams import canonical
from src.market.fees import fee_as_fraction_of_payout, total_fee
from src.market.grading import MARKET_TOTALS

SOURCE_SHARP = "sharp_consensus"
SOURCE_DERIVED = "sharp_derived"
SOURCE_MODEL = "model"

CONTRACTS_PER_UNIT = 100.0

# Extra edge required for a market derived from other sharp prices rather than
# quoted directly. A grid search over every (lambda_h, lambda_a, rho) triple that
# reproduces a given 1X2 + totals line to within 0.005 found the implied BTTS
# spanning ~0.011. That residual ambiguity is real and belongs in the threshold,
# not swept under it.
DERIVATION_PENALTY = 0.011


@dataclass
class Opportunity:
    home: str
    away: str
    market: str                    # 1x2 | totals | btts
    selection: str
    fair_prob: float
    ask: float
    fair_source: str
    league: Optional[str] = None
    kickoff: Optional[str] = None
    line: Optional[float] = None
    ticker: Optional[str] = None
    sharp_book: Optional[str] = None
    model_prob: Optional[float] = None
    notes: list = field(default_factory=list)

    @property
    def gross_edge(self) -> float:
        return self.fair_prob - self.ask

    @property
    def fee_frac(self) -> float:
        return fee_as_fraction_of_payout(self.ask, CONTRACTS_PER_UNIT)

    @property
    def derivation_penalty(self) -> float:
        return DERIVATION_PENALTY if self.fair_source == SOURCE_DERIVED else 0.0

    @property
    def net_edge(self) -> float:
        """
        Edge after fees and derivation uncertainty, in probability units.
        The only edge worth quoting.
        """
        return self.gross_edge - self.fee_frac - self.derivation_penalty

    @property
    def is_model_priced(self) -> bool:
        return self.fair_source == SOURCE_MODEL

    @property
    def is_derived(self) -> bool:
        return self.fair_source == SOURCE_DERIVED

    def __repr__(self):
        return (f"<{self.home} v {self.away} {self.market}:{self.selection} "
                f"fair {self.fair_prob:.3f} ask {self.ask:.3f} "
                f"net {self.net_edge:+.4f} [{self.fair_source}]>")


def _valid_price(p) -> bool:
    try:
        return p is not None and 0.0 < float(p) < 1.0
    except (TypeError, ValueError):
        return False


def _line_matches(market: str, fair_entry: dict, kalshi_line) -> bool:
    """
    True unless this is a totals market priced for a DIFFERENT goals line.

    Only one line is ever quoted as fair value (the odds feed gives one, the
    model is only asked for 2.5), tagged onto the fair dict as "_line". Kalshi
    lists several lines per fixture as separate markets. 2026-09-04: nothing
    checked this, so a Kalshi Over-5.5 market got priced against the Over-2.5
    fair probability and the ~45-point gap between two different bets was
    booked as an edge. Non-totals markets have no line to mismatch.
    """
    if market != MARKET_TOTALS:
        return True
    fair_line = fair_entry.get("_line")
    if fair_line is None or kalshi_line is None:
        return False
    return abs(float(fair_line) - float(kalshi_line)) < 0.01


def build_opportunities(kalshi_markets: list, fair_by_fixture: dict,
                        model_probs: dict = None,
                        allow_model_priced: bool = False) -> list:
    """
    Cross-references Kalshi prices against fair value.

    `fair_by_fixture` maps (home, away) -> {market: {selection: prob}} from the
    de-vigged sharp line. `model_probs` has the same shape and is used ONLY where
    a sharp line is absent, and only when allow_model_priced is set — the board
    says model-only pricing is a losing proposition, so it is opt-in per arm.
    """
    model_probs = model_probs or {}
    out = []

    for mkt in kalshi_markets:
        home, away = mkt.get("home"), mkt.get("away")
        if not home or not away:
            continue
        key = (canonical(home, strict=False), canonical(away, strict=False))
        market, selection = mkt.get("market"), mkt.get("selection")
        ask = mkt.get("ask")
        if not _valid_price(ask):
            continue

        fair, source, book = None, None, None
        entry = fair_by_fixture.get(key, {})
        sharp = entry.get(market, {})
        if selection in sharp and _line_matches(market, sharp, mkt.get("line")):
            fair = float(sharp[selection])
            # BTTS is not quoted by the odds feed; it is solved from the sharp
            # 1X2 and totals. Flagging it lets the edge carry the derivation
            # uncertainty rather than pretending it is a directly quoted price.
            derived = entry.get("_btts_derived") and market == "btts"
            source = SOURCE_DERIVED if derived else SOURCE_SHARP
            book = entry.get("_book")
        elif allow_model_priced:
            mp = model_probs.get(key, {}).get(market, {})
            if selection in mp and _line_matches(market, mp, mkt.get("line")):
                fair, source = float(mp[selection]), SOURCE_MODEL

        if fair is None:
            continue

        out.append(Opportunity(
            home=key[0], away=key[1], market=market, selection=selection,
            fair_prob=fair, ask=float(ask), fair_source=source,
            league=mkt.get("league"), kickoff=mkt.get("kickoff"),
            line=mkt.get("line"), ticker=mkt.get("ticker"), sharp_book=book,
            model_prob=model_probs.get(key, {}).get(market, {}).get(selection),
        ))
    return out


def filter_bettable(opportunities: list, min_edge: float = 0.02,
                    max_ask: float = 0.95, min_ask: float = 0.05) -> list:
    """
    Keeps only opportunities worth staking, sorted by net edge.

    The price bounds matter more than they look. Below 5c the 1c minimum fee is
    a 20%+ tax and any edge estimate is swamped by it; above 95c you risk a lot
    to win a little on a probability estimate that cannot be that precise.
    """
    keep = [o for o in opportunities
            if o.net_edge >= min_edge and min_ask <= o.ask <= max_ask]
    return sorted(keep, key=lambda o: o.net_edge, reverse=True)


def deduplicate_by_fixture(opportunities: list) -> list:
    """
    At most one bet per fixture per market, keeping the largest net edge.

    Without this we would stake several correlated selections on the same match
    (e.g. home win AND over 2.5), which quietly concentrates risk far beyond what
    the per-bet cap implies.
    """
    best = {}
    for o in sorted(opportunities, key=lambda o: o.net_edge, reverse=True):
        key = (o.home, o.away, o.market)
        best.setdefault(key, o)
    return sorted(best.values(), key=lambda o: o.net_edge, reverse=True)


def summarise(opportunities: list) -> dict:
    """Counts and edge distribution, for the matchweek report."""
    if not opportunities:
        return {"n": 0, "sharp_priced": 0, "model_priced": 0,
                "mean_net_edge": None, "max_net_edge": None}
    edges = [o.net_edge for o in opportunities]
    return {
        "n": len(opportunities),
        "sharp_priced": sum(1 for o in opportunities if not o.is_model_priced),
        "model_priced": sum(1 for o in opportunities if o.is_model_priced),
        "mean_net_edge": round(sum(edges) / len(edges), 4),
        "max_net_edge": round(max(edges), 4),
    }
