# SGP Sandbox Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `SgpSandboxValidator` in `src/parlay/sgp_validator.py` and integrate it into `generate_combos` of `src/parlay/parlay_engine.py` to prevent invalid and redundant same-game parlay combinations.

**Architecture:** A standalone validator class containing validation rules for same-game combos, called inside `generate_combos`.

---

### Task 1: SGP Sandbox Validator Class & Engine Integration

**Files:**
- Create: `src/parlay/sgp_validator.py`
- Modify: `src/parlay/parlay_engine.py`
- Test: `scratch/test_sgp_validator.py`

**Interfaces:**
- Consumes: `SgpSandboxValidator.validate_combo(combo)`
- Produces: Discarded invalid same-game parlays.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_sgp_validator.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestSgpValidator(unittest.TestCase):
      def test_validator_rules(self):
          from src.parlay.sgp_validator import SgpSandboxValidator
          
          # 1. Valid combo
          valid_combo = [
              {"match": ("france", "sweden"), "outcome": "home_win", "type": "game_line"},
              {"match": ("france", "sweden"), "outcome": "over_2.5", "type": "game_line"},
              {"match": ("brazil", "japan"), "outcome": "home_win", "type": "game_line"}
          ]
          self.assertTrue(SgpSandboxValidator.validate_combo(valid_combo))
          
          # 2. BTTS + Over 1.5 - Blocked
          btts_over_15 = [
              {"match": ("france", "sweden"), "outcome": "btts", "type": "game_line"},
              {"match": ("france", "sweden"), "outcome": "over_1.5", "type": "game_line"}
          ]
          self.assertFalse(SgpSandboxValidator.validate_combo(btts_over_15))
          
          # 3. BTTS + Over 2.5 - Allowed
          btts_over_25 = [
              {"match": ("france", "sweden"), "outcome": "btts", "type": "game_line"},
              {"match": ("france", "sweden"), "outcome": "over_2.5", "type": "game_line"}
          ]
          self.assertTrue(SgpSandboxValidator.validate_combo(btts_over_25))
          
          # 4. Moneyline + To Advance - Blocked
          ml_to_advance = [
              {"match": ("france", "sweden"), "outcome": "home_win", "type": "game_line"},
              {"match": ("france", "sweden"), "outcome": "to_qualify_home", "type": "game_line"}
          ]
          self.assertFalse(SgpSandboxValidator.validate_combo(ml_to_advance))
          
          # 5. Spread + Moneyline - Blocked
          spread_ml = [
              {"match": ("france", "sweden"), "outcome": "spread_home", "type": "game_line"},
              {"match": ("france", "sweden"), "outcome": "home_win", "type": "game_line"}
          ]
          self.assertFalse(SgpSandboxValidator.validate_combo(spread_ml))
          
          # 6. Player goal + Over 0.5 - Blocked
          player_over_05 = [
              {"match": ("france", "sweden"), "player": "mbappe", "type": "player_prop"},
              {"match": ("france", "sweden"), "outcome": "over_0.5", "type": "game_line"}
          ]
          self.assertFalse(SgpSandboxValidator.validate_combo(player_over_05))

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_sgp_validator.py`
  Expected: FAIL with `ModuleNotFoundError` or `ImportError` on `SgpSandboxValidator`

- [ ] **Step 3: Implement SGP Sandbox Validator class**
  Create `src/parlay/sgp_validator.py` containing:
  ```python
  class SgpSandboxValidator:
      @classmethod
      def validate_combo(cls, combo: list) -> bool:
          # Group legs by match
          match_legs = {}
          for leg in combo:
              match_legs.setdefault(leg["match"], []).append(leg)
              
          for match_key, legs in match_legs.items():
              outcomes = [leg.get("outcome") for leg in legs if leg.get("outcome") is not None]
              has_player_goals = any(leg.get("type") == "player_prop" for leg in legs)
              
              # 1. Moneyline & To Advance - Blocked
              ml_outcomes = {"home_win", "away_win", "draw"}
              qualify_outcomes = {"to_qualify_home", "to_qualify_away"}
              if any(o in ml_outcomes for o in outcomes) and any(o in qualify_outcomes for o in outcomes):
                  return False
                  
              # 2. Spread & Regulation Moneyline - Blocked
              spread_outcomes = {o for o in outcomes if "spread" in str(o)}
              if spread_outcomes and any(o in {"home_win", "away_win"} for o in outcomes):
                  return False
                  
              # 3. BTTS & Over 1.5 Goals - Blocked
              if "btts" in outcomes and "over_1.5" in outcomes:
                  return False
                  
              # 4. Redundant Player Goals & Totals (Over 0.5) - Blocked
              if has_player_goals and "over_0.5" in outcomes:
                  return False
                  
              # 5. Multi-selection counts
              ml_count = sum(1 for leg in legs if leg.get("outcome") in ml_outcomes)
              totals_count = sum(1 for leg in legs if leg.get("outcome") in {"over_0.5", "over_1.5", "over_2.5", "under_2.5"})
              spread_count = len(spread_outcomes)
              if ml_count > 1 or totals_count > 1 or spread_count > 1:
                  return False
                  
          return True
  ```

- [ ] **Step 4: Integrate into parlay engine**
  In `generate_combos` of `src/parlay/parlay_engine.py`:
  Replace the old checks (lines 316-335) with the sandbox validator:
  ```python
  from src.parlay.sgp_validator import SgpSandboxValidator
  
  # Inside loop:
  if not SgpSandboxValidator.validate_combo(combo):
      continue
  ```

- [ ] **Step 5: Run tests to verify they pass**
  Run: `python scratch/test_sgp_validator.py`
  Run the full test suite (`python -m unittest discover -s scratch`) and ensure all tests pass.

- [ ] **Step 6: Commit**
  ```bash
  git add src/parlay/sgp_validator.py src/parlay/parlay_engine.py scratch/test_sgp_validator.py
  git commit -m "feat: implement SGP Sandbox Validator to enforce Kalshi SGP rules programmatically"
  ```
