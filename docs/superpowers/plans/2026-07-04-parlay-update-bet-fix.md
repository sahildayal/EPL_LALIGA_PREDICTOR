# Parlay Bet Update Comparison Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify `update_bet` in `src/market/paper_trading.py` to compare parlay legs and stakes when checking if a bet is identical, ensuring stale parlay configurations and outdated stakes are correctly refunded and updated.

**Architecture:** Refine identity checks inside `update_bet` to compare legs list and stakes.

---

### Task 1: Parlay Bet Identity Checking Refinement

**Files:**
- Modify: `src/market/paper_trading.py`
- Test: `scratch/test_parlay_update_fix.py`

**Interfaces:**
- Consumes: `paper_trading.update_bet(...)`
- Produces: Refunded and updated active bets list.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_parlay_update_fix.py`:
  ```python
  import unittest
  import sys
  import os
  import shutil
  import tempfile
  import json
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestParlayUpdateFix(unittest.TestCase):
      def setUp(self):
          self.test_dir = tempfile.mkdtemp()
          self.patch_state_path = os.path.join(self.test_dir, "paper_trading.json")
          
          # Initialize clean state file
          from src.market import paper_trading
          self.old_state_path = paper_trading.STATE_PATH
          paper_trading.STATE_PATH = self.patch_state_path
          
          # Write clean empty portfolios state
          state = {
              "parlay_longshot": {
                  "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
                  "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
              }
          }
          with open(self.patch_state_path, "w") as f:
              json.dump(state, f)

      def tearDown(self):
          from src.market import paper_trading
          paper_trading.STATE_PATH = self.old_state_path
          shutil.rmtree(self.test_dir)

      def test_parlay_bet_update_legs_or_stake_diff(self):
          from src.market import paper_trading
          
          # Place initial card
          legs_1 = [{"home": "france", "away": "brazil", "bet_type": "Moneyline - France Win", "result": "pending"}]
          res1 = paper_trading.update_bet(
              "parlay_longshot", "magnus", "parlay", "longshot_1",
              "Longshot Card #1 (1 legs)", 33.0, 10.0, is_parlay=True, legs=legs_1
          )
          self.assertEqual(res1["action"], "placed")
          
          # Try placing identical - should return none
          res2 = paper_trading.update_bet(
              "parlay_longshot", "magnus", "parlay", "longshot_1",
              "Longshot Card #1 (1 legs)", 33.0, 10.0, is_parlay=True, legs=legs_1
          )
          self.assertEqual(res2["action"], "none")
          
          # Try placing with different stake - should update/replace and refund
          res3 = paper_trading.update_bet(
              "parlay_longshot", "magnus", "parlay", "longshot_1",
              "Longshot Card #1 (1 legs)", 2.0, 10.0, is_parlay=True, legs=legs_1
          )
          self.assertEqual(res3["action"], "updated")
          
          # Verify bankroll: 1000 - 33 initially, then + 33 refund, then - 2 = 998.0
          state = paper_trading.load_state()
          self.assertAlmostEqual(state["parlay_longshot"]["magnus"]["bankroll"], 998.0)
          
          # Try placing with different legs - should update/replace
          legs_2 = [{"home": "france", "away": "brazil", "bet_type": "Moneyline - Draw", "result": "pending"}]
          res4 = paper_trading.update_bet(
              "parlay_longshot", "magnus", "parlay", "longshot_1",
              "Longshot Card #1 (1 legs)", 2.0, 12.0, is_parlay=True, legs=legs_2
          )
          self.assertEqual(res4["action"], "updated")

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_parlay_update_fix.py`
  Expected: FAIL on `res3` action (it will incorrectly return `"none"` instead of `"updated"` because it skips stake checks).

- [ ] **Step 3: Modify code**
  In `update_bet` of `src/market/paper_trading.py`:
  Replace the block:
  ```python
      if active_idx != -1:
          old_bet = p_data["active_bets"][active_idx]
          if clean_btype(old_bet["bet_type"]) == clean_btype(new_bet_type):
              # Same bet, do nothing
              return {"action": "none", "bet": old_bet}
  ```
  with the detailed identity checking:
  ```python
      if active_idx != -1:
          old_bet = p_data["active_bets"][active_idx]
          
          is_identical = False
          if clean_btype(old_bet["bet_type"]) == clean_btype(new_bet_type):
              # Compare stakes
              if abs(old_bet.get("stake", 0.0) - new_stake) < 0.01:
                  if is_parlay:
                      old_legs = old_bet.get("legs", [])
                      new_legs = legs or []
                      if len(old_legs) == len(new_legs):
                          legs_match = True
                          for l1, l2 in zip(old_legs, new_legs):
                              if (normalize_team_name(l1.get("home")) != normalize_team_name(l2.get("home")) or 
                                  normalize_team_name(l1.get("away")) != normalize_team_name(l2.get("away")) or 
                                  clean_btype(l1.get("bet_type")) != clean_btype(l2.get("bet_type"))):
                                  legs_match = False
                                  break
                          if legs_match:
                              is_identical = True
                  else:
                      is_identical = True
                      
          if is_identical:
              # Same bet, do nothing
              return {"action": "none", "bet": old_bet}
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_parlay_update_fix.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/market/paper_trading.py scratch/test_parlay_update_fix.py
  git commit -m "fix: refine parlay update bet identity checking to compare legs and stakes"
  ```
