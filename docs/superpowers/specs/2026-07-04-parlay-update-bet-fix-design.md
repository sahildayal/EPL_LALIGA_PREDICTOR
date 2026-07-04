# Design Spec: Parlay Bet Update Comparison Fix

**Date:** 2026-07-04  
**Status:** Approved  
**Author:** Antigravity  

---

## 1. Objective
Fix a bug in the paper trading `update_bet` routine where active parlay cards are kept in-place and skipped when re-run, even if the underlying legs (matches/bets) or the desired stakes are different. 

---

## 2. Technical Design

### A. Comparison Refinement (`src/market/paper_trading.py`)
- In `update_bet(portfolio, personality, home, away, new_bet_type, new_stake, new_odds, is_parlay=False, legs=None)`:
  - If an active bet with matching keys is found, inspect if it is identical to the new bet.
  - A bet is considered **identical** only if:
    1. The normalized description type matches.
    2. The stakes match within a $0.01 tolerance (`abs(old_bet["stake"] - new_stake) < 0.01`).
    3. If it is a parlay, the actual elements in `legs` (home team, away team, bet type description) must match 1-to-1 in order.
  - If any condition fails, the old bet is treated as stale, its stake is fully refunded to the personality bankroll, the old bet is removed, and the new bet is placed.

---

## 3. Testing & Verification Plan
- **Unit Test (`scratch/test_parlay_update_fix.py`)**:
  - Place a parlay bet with a specific stake and legs list.
  - Attempt to update the same card with a different stake, and verify that `update_bet` returns `action: "placed"` or `action: "updated"`, and that the bankroll reflects the correct refund and new stake.
  - Attempt to update with different legs, and verify that the old card is replaced.
