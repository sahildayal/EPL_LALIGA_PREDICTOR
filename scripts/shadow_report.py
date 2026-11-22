"""
What the shadow ledger says so far: the edge at every threshold, and by price.

    python scripts/shadow_report.py

Reads data/processed/shadow/ (see src/market/shadow.py). Each market counts
once, at its first observation, which is the earliest moment an arm could have
bet it. Measurement only.
"""
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.market.shadow import joined  # noqa: E402

THRESHOLDS = (-0.02, -0.01, 0.0, 0.005, 0.01, 0.02)
PRICE_BUCKETS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))


def _line(label, rows, edge_key="net_edge"):
    settled = [r for r in rows if r["won"] is not None]
    closed = [r for r in rows if r.get("close_ask")]
    wins = sum(r["won"] for r in settled)
    exp_fair = sum(r["fair"] for r in settled if r.get("fair") is not None)
    exp_ask = sum(r["ask"] for r in settled)
    # Flat $1 per contract bought at the ask, before fees: P&L per market.
    pnl = sum((1.0 - r["ask"]) if r["won"] else -r["ask"] for r in settled)
    clv = [r["close_ask"] - r["ask"] for r in closed]
    print(f"{label:<22} n={len(rows):>5}  settled={len(settled):>5}  won={wins:>4}  "
          f"exp(fair)={exp_fair:7.1f}  exp(ask)={exp_ask:7.1f}  "
          f"pnl/mkt={pnl / len(settled) if settled else 0:+.4f}  "
          f"clv_pts={100 * st.mean(clv) if clv else 0:+.2f} (n={len(clv)})")


def main():
    rows = [r for r in joined() if r.get("fair") is not None]
    if not rows:
        print("shadow ledger is empty — it fills from the first stake run after 2026-11-22")
        return
    print("== sharp-priced markets by net edge at first sight ==")
    for t in THRESHOLDS:
        _line(f"net edge >= {t:+.3f}", [r for r in rows if r["net_edge"] >= t])
    print("\n== by Kalshi ask (favourite-longshot check: won vs exp(fair) vs exp(ask)) ==")
    for lo, hi in PRICE_BUCKETS:
        _line(f"ask {lo:.1f}-{hi:.1f}", [r for r in rows if lo <= r["ask"] < hi])
    print("\n== by selection side ==")
    from src.market.grading import is_no_side
    _line("YES contracts", [r for r in rows if not is_no_side(r["key"][3])])
    _line("NO contracts", [r for r in rows if is_no_side(r["key"][3])])


if __name__ == "__main__":
    main()
