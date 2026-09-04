"""
One-off maintenance script, 2026-09-04.

build_opportunities() matched a Kalshi totals market's ask against fair value
by market+selection only, ignoring which goals LINE the market was actually
for. The Odds API only quotes one line (almost always 2.5), so every totals
bet this week was priced off the Over/Under 2.5 fair probability regardless
of whether Kalshi's market was Over 4.5, 5.5, etc. -- comparing two different
bets and calling the gap an "edge". Fixed properly in src/market/edge.py;
this script voids the 24 bets that went out before the fix (9 A, 9 B, 6 C -
C's one moneyline bet, priced off the model rather than this path, is real
and left alone).

Run once via a manual workflow dispatch, then delete both.
"""
from src.market import ledger

REASON = ("Voided 2026-09-04: build_opportunities matched totals bets by "
          "market+selection only, ignoring the goals line, so this bet's "
          "'edge' compared Kalshi's price for one line against fair value "
          "computed for a different line. Not a real opportunity.")


def main():
    state = ledger.load_state()
    voided = []
    for arm, book in state["arms"].items():
        for i in range(len(book["active_bets"]) - 1, -1, -1):
            bet = book["active_bets"][i]
            if bet.get("market") == "totals":
                record = ledger.void_bet(arm, i, REASON, state=state)
                voided.append((arm, record["home"], record["away"], record["stake"]))
    ledger.save_state(state)
    print(f"Voided {len(voided)} bet(s):")
    for arm, home, away, stake in voided:
        print(f"  {arm}: {home} vs {away} (${stake})")


if __name__ == "__main__":
    main()
