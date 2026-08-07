"""
Structured bet representation and grading.

Replaces the previous substring-matching grader, which had two failure modes
that silently corrupted the ledger:

1. Any bet_type containing the substring "win" plus the home team's name graded
   as a home-win bet. Descriptions are formatted "... in {home} vs {away}", so
   "Darwin Nunez to Score (Anytime) in Liverpool vs Arsenal" was graded purely
   on whether Liverpool won. Harry Winks hit the same path.
2. Corners, to-advance, anytime-scorer, under, and any over line other than
   1.5/2.5 fell through every branch and returned False — a silent LOSS. Every
   parlay containing one of those legs was systematically graded as lost.

The fix is to stop parsing English. A bet carries structured fields; grading is
a lookup. `bet_type` survives only as a human-readable label for display.

Grading is tri-state. A bet we cannot grade raises UngradeableBet and stays
pending, rather than being recorded as a loss.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional

from src.data.team_mapping import normalize_team_name

# Markets in scope for the 2026/27 season. Corners and player props are out of
# scope for betting (no sharp reference line) but remain gradeable so the parlay
# arm can be evaluated if it ever includes them.
MARKET_1X2 = "1x2"
MARKET_TOTALS = "totals"
MARKET_BTTS = "btts"
MARKET_PLAYER_PROP = "player_prop"
MARKET_CORNERS = "corners"
MARKET_ADVANCE = "advance"

BETTABLE_MARKETS = {MARKET_1X2, MARKET_TOTALS, MARKET_BTTS}
ALL_MARKETS = BETTABLE_MARKETS | {MARKET_PLAYER_PROP, MARKET_CORNERS, MARKET_ADVANCE}


class UngradeableBet(Exception):
    """
    Raised when a bet cannot be graded from the available result data.

    Callers must leave the bet pending. Never convert this to a loss: doing so
    is what made the old grader quietly manufacture losing parlays.
    """


@dataclass
class Bet:
    """A structured wager. `label` is for humans; grading never reads it."""
    market: str
    selection: str                      # 1x2: home|draw|away · totals/corners: over|under
                                        # btts: yes|no · player_prop: player name
                                        # advance: home|away
    home: str
    away: str
    stake: float
    price: float                        # Kalshi ask in dollars, e.g. 0.52
    line: Optional[float] = None        # totals/corners only, e.g. 2.5
    prop: Optional[str] = None          # player_prop only: goals_1|goals_2|assists_1|assists_2|goal_or_assist
    label: str = ""
    league: Optional[str] = None
    kickoff: Optional[str] = None
    model_prob: Optional[float] = None
    fair_prob: Optional[float] = None   # de-vigged sharp consensus, for CLV
    closing_price: Optional[float] = None
    result: Optional[str] = None        # WIN|LOSS, set at settlement
    # Fill realism. `price` is the volume-weighted price actually obtainable for
    # this stake, walking the order book; `quoted_ask` is the top-of-book price
    # it was sized at. Keeping both makes the slippage auditable rather than
    # invisible — recording only the quote would claim a fill we never had.
    quoted_ask: Optional[float] = None
    fill_contracts: Optional[float] = None

    def __post_init__(self):
        if self.market not in ALL_MARKETS:
            raise ValueError(f"Unknown market {self.market!r}; expected one of {sorted(ALL_MARKETS)}")
        self.home = normalize_team_name(self.home)
        self.away = normalize_team_name(self.away)
        if self.market in (MARKET_TOTALS, MARKET_CORNERS) and self.line is None:
            raise ValueError(f"{self.market} bet requires a line")
        if self.market == MARKET_PLAYER_PROP and not self.prop:
            raise ValueError("player_prop bet requires a prop type")
        if not self.label:
            self.label = describe(self)

    @property
    def decimal_odds(self) -> float:
        return 1.0 / max(self.price, 1e-6)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Bet":
        known = {f for f in Bet.__dataclass_fields__}
        return Bet(**{k: v for k, v in d.items() if k in known})


def describe(bet: "Bet") -> str:
    """Human-readable label. Display only — never parsed back."""
    h, a = bet.home.title(), bet.away.title()
    if bet.market == MARKET_1X2:
        pick = {"home": f"{h} Win", "draw": "Draw", "away": f"{a} Win"}[bet.selection]
        return f"{h} vs {a} — Moneyline: {pick}"
    if bet.market == MARKET_TOTALS:
        return f"{h} vs {a} — {bet.selection.title()} {bet.line} Goals"
    if bet.market == MARKET_BTTS:
        return f"{h} vs {a} — Both Teams To Score: {bet.selection.upper()}"
    if bet.market == MARKET_CORNERS:
        return f"{h} vs {a} — {bet.selection.title()} {bet.line} Corners"
    if bet.market == MARKET_ADVANCE:
        team = h if bet.selection == "home" else a
        return f"{h} vs {a} — {team} To Advance"
    if bet.market == MARKET_PLAYER_PROP:
        return f"{h} vs {a} — {bet.selection.title()} {bet.prop.replace('_', ' ')}"
    return f"{h} vs {a} — {bet.market}"


@dataclass
class MatchResult:
    """Everything needed to grade. Missing fields make dependent bets ungradeable."""
    home: str
    away: str
    home_goals: int
    away_goals: int
    corners: Optional[int] = None                 # match total
    player_goals: dict = field(default_factory=dict)
    player_assists: dict = field(default_factory=dict)
    lineups_confirmed: bool = False               # were player stats actually retrieved?
    advanced: Optional[str] = None                # 'home'|'away' for two-legged ties

    def __post_init__(self):
        self.home = normalize_team_name(self.home)
        self.away = normalize_team_name(self.away)

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals

    def oriented_to(self, bet: "Bet") -> "MatchResult":
        """
        Returns this result with goals oriented to the bet's home/away ordering,
        so a bet stored with swapped teams still grades correctly.
        """
        if self.home == bet.home and self.away == bet.away:
            return self
        if self.home == bet.away and self.away == bet.home:
            flipped = MatchResult(
                home=self.away, away=self.home,
                home_goals=self.away_goals, away_goals=self.home_goals,
                corners=self.corners,
                player_goals=self.player_goals, player_assists=self.player_assists,
                lineups_confirmed=self.lineups_confirmed,
                advanced=None if self.advanced is None
                         else ("home" if self.advanced == "away" else "away"),
            )
            return flipped
        raise UngradeableBet(
            f"Result {self.home} vs {self.away} does not correspond to bet {bet.home} vs {bet.away}"
        )


def _match_player(name: str, table: dict) -> int:
    """Exact normalised-name lookup. No substring matching."""
    target = name.strip().lower()
    for player, count in table.items():
        if player.strip().lower() == target:
            return int(count)
    return 0


def grade(bet: Bet, result: MatchResult) -> bool:
    """
    Returns True if the bet won, False if it lost.
    Raises UngradeableBet when the result lacks the data to decide.
    """
    r = result.oriented_to(bet)

    if bet.market == MARKET_1X2:
        if bet.selection == "home":
            return r.home_goals > r.away_goals
        if bet.selection == "away":
            return r.away_goals > r.home_goals
        if bet.selection == "draw":
            return r.home_goals == r.away_goals
        raise UngradeableBet(f"Unknown 1x2 selection {bet.selection!r}")

    if bet.market == MARKET_TOTALS:
        if r.total_goals == bet.line:
            raise UngradeableBet(f"Total {r.total_goals} lands exactly on line {bet.line} (push)")
        if bet.selection == "over":
            return r.total_goals > bet.line
        if bet.selection == "under":
            return r.total_goals < bet.line
        raise UngradeableBet(f"Unknown totals selection {bet.selection!r}")

    if bet.market == MARKET_BTTS:
        both = r.home_goals >= 1 and r.away_goals >= 1
        if bet.selection == "yes":
            return both
        if bet.selection == "no":
            return not both
        raise UngradeableBet(f"Unknown BTTS selection {bet.selection!r}")

    if bet.market == MARKET_CORNERS:
        if r.corners is None:
            raise UngradeableBet("Corner count unavailable for this match")
        if r.corners == bet.line:
            raise UngradeableBet(f"Corners {r.corners} lands exactly on line {bet.line} (push)")
        if bet.selection == "over":
            return r.corners > bet.line
        if bet.selection == "under":
            return r.corners < bet.line
        raise UngradeableBet(f"Unknown corners selection {bet.selection!r}")

    if bet.market == MARKET_ADVANCE:
        if r.advanced is None:
            raise UngradeableBet("Tie progression unknown for this match")
        return r.advanced == bet.selection

    if bet.market == MARKET_PLAYER_PROP:
        # A player who did not appear in the stats tables scored zero — but only
        # if we actually retrieved the stats. Otherwise this is unknowable, and
        # guessing 'lost' is exactly the old bug.
        if not r.lineups_confirmed:
            raise UngradeableBet("Player statistics unavailable for this match")
        goals = _match_player(bet.selection, r.player_goals)
        assists = _match_player(bet.selection, r.player_assists)
        prop = bet.prop
        if prop == "goals_1":
            return goals >= 1
        if prop == "goals_2":
            return goals >= 2
        if prop == "assists_1":
            return assists >= 1
        if prop == "assists_2":
            return assists >= 2
        if prop == "goal_or_assist":
            return goals >= 1 or assists >= 1
        raise UngradeableBet(f"Unknown player prop {prop!r}")

    raise UngradeableBet(f"No grader for market {bet.market!r}")
