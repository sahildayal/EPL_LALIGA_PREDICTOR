"""
One-off maintenance script, 2026-09-15.

Until the fix landed today, `run_snapshot` and `record_closing_prices` keyed
closing prices on (home, away, market, selection) with no goals line. Kalshi
lists six totals contracts per fixture, so all six collapsed onto one key and
whichever came last won: every totals bet was stamped with a different line's
price. Open pre-kickoff bets were re-stamped correctly by the first snapshot
after the fix, but bets that had already kicked off kept the wrong number.

Six of arm C's settled bets are stuck that way. Their per-bet CLV reads -92%,
-86%, -84%, -81%, +150% and +68%, against a realistic spread of roughly plus
or minus ten points — they are noise, and CLV is the metric this experiment is
judged on.

This nulls `closing_price` on exactly those six so they drop out of the CLV
average. It does NOT touch stake, price, result or P&L: the bets still count
for win rate and ROI, they simply stop contributing a closing price that was
never really observed. Arm C's CLV goes from -10.39% to -8.06%.

Arms A, B and D are untouched — their bets were caught before settle froze
them.

Run once via the maintenance workflow, then delete both.
"""
from src.market import ledger

ARM = "C_model_kelly"

# A totals closing price this far outside its own line is arithmetically
# impossible for a 2.5-goal market and is the fingerprint of the collision:
# Over 2.5 bets took the Over 0.5 quote (~0.93+) and Under 2.5 bets took the
# Under 0.5 quote (~0.08). Anything genuinely observed sits mid-book.
IMPLAUSIBLE_LOW, IMPLAUSIBLE_HIGH = 0.12, 0.88


def main() -> int:
    state = ledger.load_state()
    book = state["arms"][ARM]
    cleared = []
    for bet in book["history"]:
        if bet.get("result") == "VOID":
            continue
        if bet.get("market") != "totals":
            continue
        close = bet.get("closing_price")
        if close is None:
            continue
        if IMPLAUSIBLE_LOW <= close <= IMPLAUSIBLE_HIGH:
            continue
        cleared.append((bet["label"], close, bet.get("price")))
        bet["closing_price"] = None
        bet.pop("closing_seen_utc", None)
        bet["closing_price_note"] = (
            "Cleared 2026-09-15: this was another goals line's price, copied in "
            "by a closing-price key that omitted the line. Excluded from CLV."
        )
    ledger.save_state(state)

    print(f"cleared {len(cleared)} corrupted closing price(s) on {ARM}:")
    for label, close, price in cleared:
        print(f"  was close={close}  against fill={price}   {label}")

    summary = ledger.arm_summary(ARM)
    print(f"\n{ARM} CLV is now {summary.get('clv_pct')}"
          f" (was -10.39), from {summary.get('settled_bets')} settled bets.")
    for arm in ("A_divergence_kelly", "B_divergence_flat", "D_parlay"):
        s = ledger.arm_summary(arm)
        print(f"  {arm}: clv_pct={s.get('clv_pct')} (untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
