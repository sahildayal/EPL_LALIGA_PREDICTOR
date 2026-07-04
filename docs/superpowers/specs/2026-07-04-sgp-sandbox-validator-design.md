# Design Spec: Same-Game Parlay (SGP) Sandbox Validator

**Date:** 2026-07-04  
**Status:** Approved  
**Author:** Antigravity  

---

## 1. Objective
Create a dedicated `SgpSandboxValidator` to model and enforce Kalshi's Same-Game Parlay (SGP) combo constraints. This acts as a local validation sandbox, preventing invalid or redundant combinations from being generated, recommended, or paper-traded.

---

## 2. Technical Design

### A. SGP Sandbox Rules
The validator will group the legs of a parlay by match. For any match containing multiple same-game legs, it enforces the following SGP rules:

1.  **BTTS & Over 1.5 Goals**: If `btts` is selected, `over_1.5` is **blocked** (redundant).
2.  **Moneyline & To Advance**: If a Regulation Time Moneyline (`home_win`, `away_win`, or `draw`) is selected, a "To Advance" outcome (`to_qualify_home` or `to_qualify_away`) is **blocked** (redundant/conflict).
3.  **Spread & Regulation Moneyline**: If a Spread outcome (e.g. `spread_home`, `spread_away`) is selected, a Regulation Time Moneyline outcome (`home_win` or `away_win`) is **blocked** (redundant/conflict).
4.  **Redundant Player Goals & Totals**: If a player anytime goalscorer prop is selected, a team goals total of `over_0.5` is **blocked** (redundant).
5.  **Multi-Selection Limits**:
    *   Max 1 Moneyline outcome per match.
    *   Max 1 Spread outcome per match.
    *   Max 1 Totals outcome per match.

### B. Sandbox Validator Class (`src/parlay/sgp_validator.py`)
- We will implement `SgpSandboxValidator` with a class method `validate_combo(combo: list) -> bool`:
  ```python
  class SgpSandboxValidator:
      @classmethod
      def validate_combo(cls, combo: list) -> bool:
          # Group legs by match
          # Run SGP rules on each group
          # Return True if valid, False otherwise
  ```
- Integrate this validation sandbox directly in `generate_combos` of `src/parlay/parlay_engine.py`:
  ```python
  from src.parlay.sgp_validator import SgpSandboxValidator
  
  # Inside combination iteration:
  if not SgpSandboxValidator.validate_combo(combo):
      continue
  ```

---

## 3. Testing & Verification Plan
- **Unit Test (`scratch/test_sgp_validator.py`)**:
  - Test case for valid standard parlays.
  - Test case for BTTS + Over 1.5 (verify blocked).
  - Test case for BTTS + Over 2.5 (verify allowed).
  - Test case for Moneyline + To Advance (verify blocked).
  - Test case for Spread + Moneyline (verify blocked).
  - Test case for Player Goals + Over 0.5 (verify blocked).
