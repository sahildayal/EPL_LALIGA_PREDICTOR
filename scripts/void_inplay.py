"""
One-off maintenance script, 2026-09-22.

Kalshi's `occurrence_datetime` is an expected RESOLUTION time, not kickoff:
real kickoff +3h on moneyline (GAME) markets and +4h on totals/BTTS, verified
to the minute against football-data kickoff times on 13 fixtures. The pipeline
stored it as `kickoff`, so every guard keyed on kickoff ran 3-4 hours late:

- the bet window let the Sunday stake runs (which drift to ~15:30 UTC) bet on
  matches already being played, priced against PRE-match fair values;
- the closing-price guard stamped mid-match prices as "closing" prices.

This script, run once before the 2026-09-22 settle:
1. voids open bets and parlays that were placed after the real kickoff;
2. reverses settled bets placed after the real kickoff to VOID (stake
   refunded, payout backed out, pnl 0), keeping the original result on record;
3. nulls every closing price captured after the real kickoff.

Nothing is invented: a void is a full refund and drops out of every metric.
Run via the maintenance workflow, then delete both.
"""
from datetime import datetime, timedelta

from src.market import ledger

OFFSET_H = {"1x2": 3}          # everything else (totals, btts) is +4h
REASON = (
    "Voided 2026-09-22: placed after the real kickoff. Kalshi's "
    "occurrence_datetime (read as kickoff) is 3-4h after the actual start, so "
    "the bet window let this through while the match was already in play, "
    "priced against a pre-match fair value."
)
CLOSE_NOTE = (
    "Cleared 2026-09-22: captured after the real kickoff, so an in-play price "
    "rather than a closing price. Excluded from CLV."
)


def _t(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def real_kickoff(item) -> datetime:
    return _t(item["kickoff"]) - timedelta(hours=OFFSET_H.get(item.get("market"), 4))


def parlay_kickoff(p) -> datetime:
    return min(real_kickoff(leg) for leg in p["legs"])


def main() -> int:
    state = ledger.load_state()
    voided_open, reversed_settled, closes_cleared = [], [], 0

    for arm, book in state["arms"].items():
        for i in range(len(book["active_bets"]) - 1, -1, -1):
            b = book["active_bets"][i]
            if _t(b["placed_utc"]) >= real_kickoff(b):
                ledger.void_bet(arm, i, REASON, state=state)
                voided_open.append((arm, b["label"], b["stake"]))

        for i in range(len(book.get("active_parlays", [])) - 1, -1, -1):
            p = book["active_parlays"][i]
            if _t(p["placed_utc"]) >= parlay_kickoff(p):
                ledger.void_parlay(arm, i, REASON, state=state)
                voided_open.append((arm, "parlay: " + " + ".join(
                    f"{l['home']}/{l['away']} {l['market']}" for l in p["legs"]), p["stake"]))

        for b in book["history"]:
            if b.get("result") not in ("WIN", "LOSS"):
                continue
            if _t(b["placed_utc"]) < real_kickoff(b):
                continue
            book["bankroll"] = round(book["bankroll"] + b["stake"] - b.get("payout", 0.0), 2)
            b["original_result"], b["original_pnl"] = b["result"], b.get("pnl")
            b["result"], b["pnl"], b["payout"] = "VOID", 0.0, b["stake"]
            b["void_reason"] = REASON
            reversed_settled.append((arm, b["label"], b["original_result"], b["original_pnl"]))

        for b in book["history"] + book["active_bets"]:
            if b.get("result") == "VOID" or b.get("closing_price") is None:
                continue
            seen = b.get("closing_seen_utc")
            if seen and _t(seen) >= real_kickoff(b):
                b["closing_price"] = None
                b.pop("closing_seen_utc", None)
                b["closing_price_note"] = CLOSE_NOTE
                closes_cleared += 1

        for p in book.get("active_parlays", []):
            seen = p.get("closing_seen_utc")
            if seen and _t(seen) >= parlay_kickoff(p):
                p.pop("closing_price", None)
                p.pop("closing_seen_utc", None)
                for leg in p["legs"]:
                    leg["closing_price"] = None
                p["closing_price_note"] = CLOSE_NOTE
                closes_cleared += 1

    ledger.save_state(state)

    print(f"voided {len(voided_open)} open in-play bet(s)/parlay(s):")
    for arm, label, stake in voided_open:
        print(f"  {arm}: {label}  (${stake:,.2f} refunded)")
    print(f"\nreversed {len(reversed_settled)} settled in-play bet(s) to VOID:")
    for arm, label, res, pnl in reversed_settled:
        print(f"  {arm}: {label}  (was {res}, pnl {pnl:+,.2f})")
    print(f"\ncleared {closes_cleared} in-play closing price(s)")
    print()
    for arm in state["arms"]:
        s = ledger.arm_summary(arm, state=state)
        print(f"  {arm}: bankroll {state['arms'][arm]['bankroll']:,.2f}  "
              f"settled {s.get('settled_bets')}  clv {s.get('clv_pct')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
