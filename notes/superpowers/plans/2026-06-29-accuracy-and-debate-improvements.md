# Implementation Plan: Predictive Accuracy & Enforced AI Debates

This plan integrates the newly completed time-decayed Dixon-Coles regressor, disables mock fallback debates (requiring actual Gemini AI execution), and implements Fractional Kelly sizing for quant paper bets.

## Proposed Changes

### 1. Integrate Time-Decayed Dixon-Coles Regressor
- **File**: `src/predictor.py`
- **Action**: 
  - Add `get_fitted_dixon_coles()` helper to load the master dataset, compute `days_ago`, fit the `DixonColesRegressor`, and cache the parameter array in the SQLite database to avoid expensive recalculations.
  - Update `predict_match` to use the cached fitted `DixonColesRegressor` probabilities instead of manually setting attack/defense parameters using inverted log-conceded values.

### 2. Enforce Gemini API Key for Debates
- **File**: `src/market/llm.py`
- **Action**:
  - Modify `generate_debate` to raise a `RuntimeError` if `GEMINI_API_KEY` is not present, disabling `_get_fallback_debate` completely to prevent mock/simulated debates from yielding confusing or hardcoded plays.

### 3. Implement Fractional Kelly Criterion Sizing
- **File**: `main.py`
- **Action**:
  - In the `predict` CLI command, compute SIGMABALLS' stake using the **Fractional Kelly Criterion** (Quarter-Kelly):
    $$f^* = \frac{p \times b - (1 - p)}{b}$$
    where $b = \text{odds} - 1$ and $p = \text{probability}$.
  - Scale by $0.25$ and cap the maximum stake at **15%** of the bankroll (minimum 2% to ensure active play if edge is positive).
  - Big D will continue to use a flat **10%** stake as it matches his intuitive scout eye-test profile.

## Verification Plan

### Test Cases (TDD)
- **File**: `scratch/test_predictor_improvements.py`
- **Tests**:
  1. `test_dixon_coles_regressor_integration`: Verify `get_fitted_dixon_coles` correctly fits and returns a regressor.
  2. `test_debate_key_enforcement`: Verify calling `generate_debate` raises a `RuntimeError` if `GEMINI_API_KEY` is missing (temporarily mocking the key environment variables).
  3. `test_fractional_kelly_sizing`: Verify mathematical correctness of the Kelly sizing formula for various probability/price configurations.
