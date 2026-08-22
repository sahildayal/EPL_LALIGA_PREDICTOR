"""
Season ledger: four independent $10,000 books for the 2026/27 experiment.

Replaces the previous 8-book magnus/athena x 4-portfolio structure, which mixed
persona roleplay into bet sizing. Arms differ in exactly one variable each, so
the season's result is interpretable:

    A  divergence + quarter-Kelly     flagship
    B  divergence + flat 1%           A/B isolates the staking rule
    C  model-only  + quarter-Kelly    A/C isolates the edge source
    D  parlay / SGP                   does the parlay arm clear its own vig?

No reset and no reload. An arm that busts stays busted; that is a real result.

Grading is delegated to src.market.grading, which is tri-state: a bet that
cannot be graded stays pending rather than being recorded as a loss.
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional

from src.market.grading import Bet, MatchResult, grade, UngradeableBet
from src.market.parlay_arm import Parlay

DATA_DIR = os.path.join("data", "processed")
LEDGER_PATH = os.path.join(DATA_DIR, "season_ledger.json")
ARCHIVE_PATH = os.path.join(DATA_DIR, "ledger_archive_2026wc.json")

SEASON = "2026-27"
STARTING_BANKROLL = 10_000.0
# v3 adds parlay storage for arm D. A parlay spans several fixtures, so it
# cannot live in `active_bets`, whose settlement matches a single fixture.
SCHEMA_VERSION = 3

ARMS = {
    "A_divergence_kelly": "Divergence + quarter-Kelly",
    "B_divergence_flat": "Divergence + flat 1%",
    "C_model_kelly": "Model-only + quarter-Kelly",
    "D_parlay": "Parlay / SGP",
}


class InsufficientBankroll(Exception):
    """Raised when an arm cannot cover a stake. Arms are never reloaded."""


def _new_arm(label: str) -> dict:
    return {
        "label": label,
        "bankroll": STARTING_BANKROLL,
        "starting_bankroll": STARTING_BANKROLL,
        "active_bets": [],
        "history": [],
        # Arm D only, but present on every arm so the shape is uniform and
        # reporting code never has to branch on which arm it is reading.
        "active_parlays": [],
        "parlay_history": [],
    }


def new_state() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "season": SEASON,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "arms": {key: _new_arm(label) for key, label in ARMS.items()},
    }


def _migrate(state: dict) -> dict:
    """
    Brings an older ledger up to the current schema, or refuses.

    Only strictly ADDITIVE migrations are performed. A migration that reshapes or
    reinterprets existing bet records could silently rewrite the season's record
    after the fact, which is the one thing a public, timestamped ledger exists to
    prevent. Anything beyond adding empty containers raises.
    """
    version = state.get("schema_version")
    if version == SCHEMA_VERSION:
        return state
    if version == 2:
        # v2 -> v3: parlay containers. Purely additive; no existing record is
        # read, moved or reinterpreted, so no result can change.
        for book in state.get("arms", {}).values():
            book.setdefault("active_parlays", [])
            book.setdefault("parlay_history", [])
        state["schema_version"] = SCHEMA_VERSION
        state.setdefault("migrations", []).append({
            "utc": datetime.now(timezone.utc).isoformat(),
            "from": 2, "to": SCHEMA_VERSION,
            "note": "added active_parlays/parlay_history for arm D",
        })
        return state
    raise ValueError(
        f"Ledger at {LEDGER_PATH} is schema v{version}, expected v{SCHEMA_VERSION}, "
        "and no additive migration exists for it. Refusing to guess: archive it "
        "explicitly with archive_legacy_ledger()."
    )


def load_state() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(LEDGER_PATH):
        state = new_state()
        save_state(state)
        return state
    with open(LEDGER_PATH, "r") as f:
        state = json.load(f)
    state = _migrate(state)
    for key in ARMS:
        if key not in state["arms"]:
            raise ValueError(f"Ledger is missing arm {key!r}; refusing to silently recreate it mid-season.")
    return state


def save_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = LEDGER_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, LEDGER_PATH)     # atomic; a crash mid-write cannot corrupt the ledger


def archive_legacy_ledger(source: str = None, dest: str = None) -> Optional[str]:
    """
    Moves the old World Cup paper_trading.json aside. Those bets were priced
    against markets that no longer exist and many were graded by the previous
    buggy grader, so folding them into the season experiment would contaminate it.
    Returns the archive path, or None if there was nothing to archive.
    """
    source = source or os.path.join(DATA_DIR, "paper_trading.json")
    dest = dest or ARCHIVE_PATH
    if not os.path.exists(source):
        return None
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(source, "r") as f:
        legacy = json.load(f)
    with open(dest, "w") as f:
        json.dump(
            {
                "archived_utc": datetime.now(timezone.utc).isoformat(),
                "note": (
                    "2026 World Cup paper trading, archived at the start of the 2026/27 season "
                    "rebuild. Bets here were priced against expired markets and graded by the "
                    "pre-rebuild string grader; treat their results as unreliable."
                ),
                "data": legacy,
            },
            f,
            indent=2,
        )
    os.remove(source)
    return dest


# --- Placing -----------------------------------------------------------------

def place_bet(arm: str, bet: Bet, state: dict = None) -> dict:
    """Debits the stake and records the bet. Raises rather than silently clipping."""
    if arm not in ARMS:
        raise ValueError(f"Unknown arm {arm!r}; expected one of {sorted(ARMS)}")
    owns_state = state is None
    state = state or load_state()
    book = state["arms"][arm]

    if bet.stake <= 0:
        raise ValueError(f"Stake must be positive, got {bet.stake}")
    if bet.stake > book["bankroll"] + 1e-9:
        raise InsufficientBankroll(
            f"Arm {arm} has ${book['bankroll']:.2f}, cannot stake ${bet.stake:.2f}. Arms are never reloaded."
        )

    book["bankroll"] = round(book["bankroll"] - bet.stake, 2)
    record = bet.to_dict()
    record["placed_utc"] = datetime.now(timezone.utc).isoformat()
    book["active_bets"].append(record)

    if owns_state:
        save_state(state)
    return record


def place_parlay(arm: str, parlay: Parlay, state: dict = None) -> dict:
    """Debits a parlay stake once and records it with every leg ungraded."""
    if arm not in ARMS:
        raise ValueError(f"Unknown arm {arm!r}; expected one of {sorted(ARMS)}")
    owns_state = state is None
    state = state or load_state()
    book = state["arms"][arm]

    if parlay.stake <= 0:
        raise ValueError(f"Stake must be positive, got {parlay.stake}")
    if parlay.stake > book["bankroll"] + 1e-9:
        raise InsufficientBankroll(
            f"Arm {arm} has ${book['bankroll']:.2f}, cannot stake ${parlay.stake:.2f}. Arms are never reloaded."
        )

    book["bankroll"] = round(book["bankroll"] - parlay.stake, 2)
    record = parlay.to_dict()
    record["placed_utc"] = datetime.now(timezone.utc).isoformat()
    book["active_parlays"].append(record)

    if owns_state:
        save_state(state)
    return record


# --- Settling ----------------------------------------------------------------

def settle_match(result: MatchResult, state: dict = None) -> dict:
    """
    Grades every active bet touching this fixture across all four arms.

    Returns {"settled": [...], "pending": [...]} where `pending` lists bets that
    matched the fixture but could not be graded — those stay active and are
    reported, never converted to losses.
    """
    owns_state = state is None
    state = state or load_state()
    settled, pending = [], []

    for arm_key, book in state["arms"].items():
        still_active = []
        for record in book["active_bets"]:
            try:
                bet = Bet.from_dict(record)
            except Exception as exc:
                pending.append({"arm": arm_key, "bet": record, "reason": f"unreadable bet: {exc}"})
                still_active.append(record)
                continue

            # Does this bet concern this fixture at all?
            teams_bet = {bet.home, bet.away}
            if teams_bet != {result.home, result.away}:
                still_active.append(record)
                continue

            try:
                won = grade(bet, result)
            except UngradeableBet as exc:
                record.setdefault("grading_notes", []).append(
                    {"utc": datetime.now(timezone.utc).isoformat(), "reason": str(exc)}
                )
                pending.append({"arm": arm_key, "bet": record, "reason": str(exc)})
                still_active.append(record)
                continue

            payout = bet.stake * bet.decimal_odds if won else 0.0
            if won:
                book["bankroll"] = round(book["bankroll"] + payout, 2)
            record["result"] = "WIN" if won else "LOSS"
            record["payout"] = round(payout, 2)
            record["pnl"] = round(payout - bet.stake, 2)
            record["settled_utc"] = datetime.now(timezone.utc).isoformat()
            book["history"].append(record)
            settled.append({"arm": arm_key, "bet": record})

        book["active_bets"] = still_active

    p_out = _settle_parlays(result, state)

    if owns_state:
        save_state(state)
    return {
        "settled": settled,
        "pending": pending,
        "parlays_settled": p_out["settled"],
        "parlays_pending": p_out["pending"],
    }


def _settle_parlays(result: MatchResult, state: dict) -> dict:
    """
    Grades the legs of every open parlay that touch this fixture.

    Two rules that are easy to get wrong:

    * **A parlay dies on its first losing leg.** Once any leg loses the wager is
      worthless, so it settles immediately as a LOSS rather than waiting for the
      remaining fixtures. Holding it open would misstate open exposure and delay
      the loss out of the matchweek it belongs to.
    * **A leg we cannot grade leaves the parlay open.** Same rule as singles: an
      ungradeable leg is recorded and left pending, never resolved as a loss.
    """
    settled, pending = [], []

    for arm_key, book in state["arms"].items():
        still_open = []
        for record in book.get("active_parlays", []):
            try:
                parlay = Parlay.from_dict(record)
            except Exception as exc:
                pending.append({"arm": arm_key, "parlay": record,
                                "reason": f"unreadable parlay: {exc}"})
                still_open.append(record)
                continue

            for leg_record, leg in zip(record["legs"], parlay.legs):
                if leg_record.get("result"):
                    continue
                if {leg.home, leg.away} != {result.home, result.away}:
                    continue
                try:
                    won = grade(leg.to_bet(), result)
                except UngradeableBet as exc:
                    record.setdefault("grading_notes", []).append(
                        {"utc": datetime.now(timezone.utc).isoformat(),
                         "leg": leg.to_bet().label, "reason": str(exc)})
                    pending.append({"arm": arm_key, "parlay": record, "reason": str(exc)})
                    continue
                leg_record["result"] = "WIN" if won else "LOSS"

            results = [l.get("result") for l in record["legs"]]
            stake = float(record["stake"])

            if "LOSS" in results:
                payout = 0.0
            elif all(r == "WIN" for r in results):
                payout = stake / max(float(record["ask"]), 1e-9)
            else:
                still_open.append(record)
                continue

            if payout > 0:
                book["bankroll"] = round(book["bankroll"] + payout, 2)
            record["result"] = "WIN" if payout > 0 else "LOSS"
            record["payout"] = round(payout, 2)
            record["pnl"] = round(payout - stake, 2)
            record["settled_utc"] = datetime.now(timezone.utc).isoformat()
            book.setdefault("parlay_history", []).append(record)
            settled.append({"arm": arm_key, "parlay": record})

        book["active_parlays"] = still_open

    return {"settled": settled, "pending": pending}


def void_parlay(arm: str, index: int, reason: str, state: dict = None) -> dict:
    """
    Refunds an open parlay in full and marks it VOID.

    An exchange would normally REDUCE a parlay when one fixture is postponed,
    dropping that leg and repricing the rest. We void the whole wager instead,
    deliberately. Reducing would mean re-deriving a joint probability and a
    synthetic combined ask for a bet that has already been placed, and any error
    in that re-derivation would quietly rewrite the recorded result of a live
    bet. A full refund is excluded from every metric, so it is unbiased; a
    mis-reduced parlay is not.
    """
    owns = state is None
    state = state or load_state()
    book = state["arms"][arm]
    if not 0 <= index < len(book.get("active_parlays", [])):
        raise IndexError(f"arm {arm} has no active parlay at index {index}")

    record = book["active_parlays"].pop(index)
    book["bankroll"] = round(book["bankroll"] + float(record["stake"]), 2)
    record["result"] = "VOID"
    record["pnl"] = 0.0
    record["payout"] = round(float(record["stake"]), 2)
    record["void_reason"] = reason
    record["settled_utc"] = datetime.now(timezone.utc).isoformat()
    book.setdefault("parlay_history", []).append(record)

    if owns:
        save_state(state)
    return record


# --- Reporting ---------------------------------------------------------------

def _kicked_off(entry, now=None) -> bool:
    """
    True when this bet's fixture has already started.

    A price observed after kickoff is not a closing price — it is an in-play
    price, and on a market Kalshi leaves open during the match it can be
    arbitrarily far from the close. Stamping one would not merely lose CLV for
    that bet, it would overwrite a good earlier stamp with a worse number and
    report it as the close.

    An unparseable or missing kickoff returns False: active bets always carry
    one (undated markets are refused at staking), so this is a guard against
    corruption, not a filter we want silently dropping stamps.
    """
    raw = entry.get("kickoff")
    if not raw:
        return False
    try:
        ko = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) >= ko


def record_closing_prices(prices: dict, state: dict = None, now=None) -> int:
    """
    Stamps the latest observed PRE-KICKOFF Kalshi price onto every active bet.

    Called by the read-only snapshot job. CLV is the season's primary metric
    because at ~150 bets per arm, P&L is dominated by variance while CLV
    converges far faster — but it only exists if we capture the closing price
    before the market settles.

    `prices` maps (home, away, market, selection) -> price. Later snapshots
    overwrite earlier ones, so the final pre-kickoff call wins — and a fixture
    that has already started is skipped entirely, so "final pre-kickoff" is
    literally what gets kept rather than merely what usually got kept. Without
    that, the Saturday runs could clobber a Friday-night fixture's good Friday
    18:00 stamp with a post-match price.
    """
    owns = state is None
    state = state or load_state()
    stamped = 0
    for book in state["arms"].values():
        for bet in book["active_bets"]:
            if _kicked_off(bet, now):
                continue
            key = (bet.get("home"), bet.get("away"), bet.get("market"), bet.get("selection"))
            if key in prices:
                bet["closing_price"] = float(prices[key])
                bet["closing_seen_utc"] = datetime.now(timezone.utc).isoformat()
                stamped += 1
        # Parlay CLV is measured on the combined price, so a parlay only counts
        # once EVERY leg has been seen. A partial stamp would compare an entry
        # price against a mixture of entry and closing legs, which is not CLV.
        for parlay in book.get("active_parlays", []):
            for leg in parlay.get("legs", []):
                if _kicked_off(leg, now):
                    continue
                key = (leg.get("home"), leg.get("away"), leg.get("market"), leg.get("selection"))
                if key in prices:
                    leg["closing_price"] = float(prices[key])
            closes = [l.get("closing_price") for l in parlay.get("legs", [])]
            if closes and all(c not in (None, 0) for c in closes):
                combined = 1.0
                for c in closes:
                    combined *= float(c)
                parlay["closing_price"] = combined
                parlay["closing_seen_utc"] = datetime.now(timezone.utc).isoformat()
                stamped += 1
    if owns:
        save_state(state)
    return stamped


def void_bet(arm: str, index: int, reason: str, state: dict = None) -> dict:
    """
    Refunds a staked bet and marks it VOID.

    Mirrors what an exchange does when a fixture is postponed or a market is
    cancelled: the bet never happened. Voided bets are excluded from ROI, win
    rate and CLV so they neither help nor drag on the arm's measured performance.
    """
    owns = state is None
    state = state or load_state()
    book = state["arms"][arm]
    if not 0 <= index < len(book["active_bets"]):
        raise IndexError(f"arm {arm} has no active bet at index {index}")

    record = book["active_bets"].pop(index)
    book["bankroll"] = round(book["bankroll"] + record["stake"], 2)
    record["result"] = "VOID"
    record["pnl"] = 0.0
    record["payout"] = record["stake"]
    record["void_reason"] = reason
    record["settled_utc"] = datetime.now(timezone.utc).isoformat()
    book["history"].append(record)

    if owns:
        save_state(state)
    return record


def void_fixture(home: str, away: str, reason: str, state: dict = None) -> list:
    """Voids every active bet on a fixture, across all arms."""
    from src.data.canonical_teams import canonical
    owns = state is None
    state = state or load_state()
    h, a = canonical(home, strict=False), canonical(away, strict=False)
    voided = []
    for arm, book in state["arms"].items():
        for i in range(len(book["active_bets"]) - 1, -1, -1):
            bet = book["active_bets"][i]
            if {bet.get("home"), bet.get("away")} == {h, a}:
                voided.append({"arm": arm, "bet": void_bet(arm, i, reason, state=state)})
        # A parlay with a leg on this fixture can never be settled, so it goes too.
        for i in range(len(book.get("active_parlays", [])) - 1, -1, -1):
            parlay = book["active_parlays"][i]
            if any({l.get("home"), l.get("away")} == {h, a} for l in parlay.get("legs", [])):
                voided.append({"arm": arm,
                               "parlay": void_parlay(arm, i, reason, state=state)})
    if owns:
        save_state(state)
    return voided


def arm_summary(arm: str, state: dict = None) -> dict:
    state = state or load_state()
    book = state["arms"][arm]

    # Parlays are wagers like any other and belong in the arm's P&L, win rate and
    # CLV. Their combined ask plays the role a single bet's price plays, so they
    # are normalised onto the same shape rather than reported separately — arm D
    # has to be comparable to A/B/C for the season's question to have an answer.
    def _as_wager(p: dict) -> dict:
        w = dict(p)
        w["price"] = p.get("ask")
        return w

    all_history = list(book["history"]) + [
        _as_wager(p) for p in book.get("parlay_history", [])]
    all_active = list(book["active_bets"]) + list(book.get("active_parlays", []))

    # Voided bets never happened; including them would dilute win rate and ROI
    # with rows that had no outcome.
    history = [b for b in all_history if b.get("result") != "VOID"]
    voided = [b for b in all_history if b.get("result") == "VOID"]
    wins = sum(1 for b in history if b.get("result") == "WIN")
    staked = sum(b.get("stake", 0.0) for b in history)
    pnl = sum(b.get("pnl", 0.0) for b in history)
    exposure = sum(b.get("stake", 0.0) for b in all_active)

    # Closing Line Value: the primary metric. P&L over ~150 bets is mostly noise.
    clv_pairs = [
        (b["price"], b["closing_price"])
        for b in history
        if b.get("closing_price") not in (None, 0)
    ]
    clv = None
    if clv_pairs:
        clv = round(sum((c - p) / p for p, c in clv_pairs) / len(clv_pairs) * 100, 2)

    return {
        "arm": arm,
        "label": book["label"],
        "bankroll": round(book["bankroll"], 2),
        "exposure": round(exposure, 2),
        "equity": round(book["bankroll"] + exposure, 2),
        "settled_bets": len(history),
        "voided_bets": len(voided),
        "open_bets": len(all_active),
        "open_parlays": len(book.get("active_parlays", [])),
        "settled_parlays": sum(1 for p in book.get("parlay_history", [])
                               if p.get("result") != "VOID"),
        "wins": wins,
        "win_rate": round(wins / len(history) * 100, 1) if history else None,
        "total_staked": round(staked, 2),
        "pnl": round(pnl, 2),
        "roi_pct": round(pnl / staked * 100, 2) if staked else None,
        "clv_pct": clv,
        "is_bust": book["bankroll"] < 0.01 and not all_active,
    }


def season_summary(state: dict = None) -> list:
    state = state or load_state()
    return [arm_summary(arm, state) for arm in ARMS]
