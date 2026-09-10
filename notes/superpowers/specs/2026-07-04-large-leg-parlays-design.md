# Design Spec: High-Leg Parlay Combinations (Up to 12 Legs)

**Date:** 2026-07-04  
**Status:** Approved  
**Author:** Antigravity  

---

## 1. Objective
Support "insane big combos" by allowing the parlay engine to generate portfolios of up to 12 legs. To prevent combinatorial explosion and CPU/memory slowdowns, we dynamically scale the candidate limit based on the requested maximum leg count.

---

## 2. Technical Design

### A. Candidate Capping & Combinatorial Control (`src/parlay/parlay_engine.py`)
- In `generate_combos(self, match_data, max_legs=5, min_odds=5.0, max_odds=150.0)`:
  - If `max_legs > 5`, limit the candidate legs list to the top **15** items with the highest model-to-market edge.
  - If `max_legs <= 5`, keep the candidate legs list capped at the top **25** items.
- Scale the combination generator range up to `min(max_legs, len(candidates))`.
- This ensures that for a 12-leg parlay, the maximum combinations evaluated is at most $\sum_{r=3}^{12} \binom{15}{r} = 32,647$ combinations, executing in less than 0.2 seconds in Python.

### B. CLI Target Multipliers (`main.py`)
- In `run_parlay(longshot=True)`:
  - Call `engine.generate_combos(matches, max_legs=12, min_odds=50.0, max_odds=400.0)`.
- In `run_parlay(longshot=False)`:
  - Call `engine.generate_combos(matches, max_legs=6, min_odds=5.0, max_odds=150.0)`.

---

## 3. Testing & Verification Plan
- **Unit Test (`scratch/test_large_legs.py`)**:
  - Verify that `generate_combos` executes successfully and returns combos with 5+ legs when `max_legs=12` is requested.
  - Verify that execution finishes within 0.5 seconds.
