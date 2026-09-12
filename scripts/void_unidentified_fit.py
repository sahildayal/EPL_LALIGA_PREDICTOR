"""
One-off maintenance script, 2026-09-12.

The 2026-09-11 Dixon-Coles fit identified just-promoted clubs from their
current season alone (365-day decay), and with ~3 matches the likelihood is
flat enough that L-BFGS-B pinned parameters at the box bound set in
DixonColes.fit: hull defence EXACTLY -3.000, coventry attack EXACTLY -3.000,
with malaga (-1.450) and deportivo la coruna (+0.434) far outside their
league's own quintiles on ~4 effective matches. That priced Chelsea to score
0.088 goals at home and Hull to win at Stamford Bridge at 55% against a 7%
market ask.

Voids arm C's open bets on fixtures involving those four clubs. Everything
else stands: the Sep 6 bets predate the bad fit, and Real Madrid v Rayo
Vallecano is between two clubs with ~52 effective matches each and prices out
sane (lambdas 2.24/0.65, over2.5 0.551).

Fixed in the pipeline by _shrink_to_prior in src/pipeline/matchweek.py. Run
once via the maintenance workflow, then delete both.
"""
from src.market import ledger

ARM = "C_model_kelly"

# Clubs the 2026-09-11 diagnostic showed as under-identified (effective
# weighted sample 3-4 matches against ~52 for an established side).
UNIDENTIFIED = {"hull", "coventry", "malaga", "deportivo la coruna"}

REASON = (
    "Voided 2026-09-12: priced by the 2026-09-11 Dixon-Coles fit, in which a "
    "just-promoted club was identified by ~3 current-season matches and the "
    "optimiser pinned its attack/defence at the +/-3 box bound rather than "
    "converging. Not a model view, an optimiser artifact."
)


def main() -> int:
    state = ledger.load_state()
    book = state["arms"][ARM]
    voided = []
    for i in range(len(book["active_bets"]) - 1, -1, -1):
        bet = book["active_bets"][i]
        if {bet.get("home"), bet.get("away")} & UNIDENTIFIED:
            rec = ledger.void_bet(ARM, i, REASON, state=state)
            voided.append((rec["label"], rec["stake"]))
    ledger.save_state(state)

    print(f"voided {len(voided)} bet(s), refunding "
          f"${sum(s for _, s in voided):,.2f}:")
    for label, stake in reversed(voided):
        print(f"  {label}  (${stake:,.2f})")
    print(f"\n{ARM} bankroll now {state['arms'][ARM]['bankroll']:,.2f}, "
          f"{len(book['active_bets'])} bet(s) still open:")
    for bet in book["active_bets"]:
        print(f"  KEPT  {bet['label']}  (${bet['stake']:,.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
