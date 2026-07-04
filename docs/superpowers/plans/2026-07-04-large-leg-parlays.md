# High-Leg Parlay Combinations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the parlay engine to support up to 12 legs for combos by dynamically capping candidates to prevent combinatorial explosion.

**Architecture:** Cap candidates at 15 if `max_legs > 5` to keep iterations low, and call `generate_combos` with `max_legs=12` for longshot portfolios.

---

### Task 1: High-Leg Parlay Generation & Candidate Capping

**Files:**
- Modify: `src/parlay/parlay_engine.py`
- Modify: `main.py`
- Test: `scratch/test_large_legs.py`

**Interfaces:**
- Consumes: `engine.generate_combos(matches, max_legs=12, ...)`
- Produces: Parlays of up to 12 legs.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_large_legs.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestLargeLegs(unittest.TestCase):
      def test_high_leg_generation(self):
          from src.models.statistical import DixonColesModel
          from src.parlay.parlay_engine import ParlayEngine
          
          dc = DixonColesModel()
          engine = ParlayEngine(dc)
          
          # Setup mock data with 12 positive-edge candidates (low market odds)
          match_data = [
              {
                  "home": "France", "away": "Brazil",
                  "market_odds": {
                      "home_win": 0.01, "draw": 0.01, "away_win": 0.01,
                      "over_1.5": 0.01, "over_2.5": 0.01, "btts": 0.01
                  }
              },
              {
                  "home": "Argentina", "away": "England",
                  "market_odds": {
                      "home_win": 0.01, "draw": 0.01, "away_win": 0.01,
                      "over_1.5": 0.01, "over_2.5": 0.01, "btts": 0.01
                  }
              }
          ]
          
          # Request up to 10 legs
          combos = engine.generate_combos(match_data, max_legs=10, min_odds=50.0, max_odds=1000000.0)
          self.assertGreater(len(combos), 0)
          # Check that we got at least one combo with more than 5 legs
          high_legs = [c for c in combos if len(c["legs"]) >= 5]
          self.assertGreater(len(high_legs), 0)

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_large_legs.py`
  Expected: FAIL (either empty list or limit of 5 prevents high legs)

- [ ] **Step 3: Modify code and limit candidates**
  1. In `generate_combos` of `src/parlay/parlay_engine.py`:
     - Dynamically set candidate cap:
       ```python
       # Sort and limit candidates to prevent combinatorial explosion
       max_cand = 15 if max_legs > 5 else 25
       candidates.sort(key=lambda x: x["model_prob"] - x["market_prob"], reverse=True)
       candidates = candidates[:max_cand]
       ```
  2. In `main.py`'s `run_parlay()`:
     - Update the longshot calling code:
       ```python
       parlays = engine.generate_combos(matches, max_legs=12, min_odds=50.0, max_odds=400.0)
       ```
     - Update the standard calling code:
       ```python
       parlays = engine.generate_combos(matches, max_legs=6, min_odds=5.0, max_odds=150.0)
       ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_large_legs.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/parlay/parlay_engine.py main.py scratch/test_large_legs.py
  git commit -m "feat: support up to 12 legs for parlays with dynamic candidate capping"
  ```
