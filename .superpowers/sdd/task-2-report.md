# Task 2 Report: Dixon-Coles Time Decay Model & Parameter Estimator

## Implementation Details
We implemented the Dixon-Coles goal expectation regressor model with dynamic parameter estimation and exponential time-decay weighting.
Specifically, the class `DixonColesRegressor` in `src/models/dixon_coles_decay.py` includes:
- Attacking parameters (`alpha`), defensive parameters (`beta`), home advantage (`gamma`), and correlation adjustment (`rho`).
- Exponential time weighting of log-likelihood using parameters `xi` and match age `days_ago`.
- Numerical stability improvements using `np.clip` on the exponent terms to prevent potential overflow/underflow during parameter optimization under SciPy `minimize`.
- A fallback system in the event optimization doesn't converge or encounters issues, defaulting to safe parameter estimates.

## Test Results
We ran the unit tests locally under `scratch/test_dixon_coles_decay.py` and all tests passed successfully.

### Test suite details:
- `test_regressor_fit`: Verifies parameter estimation converges and produces valid probabilities within the `[0, 1]` range.
- `test_unknown_teams`: Verifies that predicting matches containing teams not present in the training set falls back to the default probability split `(0.33, 0.33, 0.34)`.
- `test_fallback_fit_failure`: Verifies that minimal input datasets still fit without error, and output probabilities continue to sum to 1.0.

## TDD Evidence
### RED Phase
- **Command Run:** `python scratch/test_dixon_coles_decay.py`
- **Output:**
  ```
  Traceback (most recent call last):
    File "C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor\scratch\test_dixon_coles_decay.py", line 6, in <module>
      from src.models.dixon_coles_decay import DixonColesRegressor
  ModuleNotFoundError: No module named 'src.models.dixon_coles_decay'
  ```
- **Why Failure Expected:** The target module `src.models.dixon_coles_decay` did not exist yet, causing the initial import to fail.

### GREEN Phase
- **Command Run:** `python scratch/test_dixon_coles_decay.py`
- **Output:**
  ```
  ...
  ----------------------------------------------------------------------
  Ran 3 tests in 0.065s

  OK
  ```

## Files Changed
- Created: [src/models/dixon_coles_decay.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/models/dixon_coles_decay.py)
- Created: [scratch/test_dixon_coles_decay.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_dixon_coles_decay.py)

## Self-Review Findings
- **Completeness:** Implemented all required interfaces (`DixonColesRegressor(xi=0.0019)`, `DixonColesRegressor.fit(df)`, `DixonColesRegressor.predict_match_probs(home, away)`).
- **Quality:** Capped exponent terms using `np.clip` to prevent potential numeric overflow warnings during scipy optimization.
- **Testing:** The tests cover typical success paths, unknown team fallback paths, minimal datasets, and verify that the output probabilities are properly normalized and sum to 1.0.

## Fixes Applied

1. **ValueError on Empty Fitting**:
   - Added checks in `fit()` in `src/models/dixon_coles_decay.py` to check if `df` is empty, or lacks `home_team`/`away_team` columns, or if `n_teams <= 1`.
   - If any of these are true, immediately populates fallback parameters and returns early without causing a `ValueError` in SciPy parameter initialization.

2. **Negative Probability Protection in Prediction**:
   - In `predict_match_probs()`, added protection checking `tau_val <= 0` and setting it to `1e-10` to avoid potential non-positive/negative probabilities during calculation.

3. **Method Signature Rename**:
   - Renamed parameter names from `home_team` and `away_team` to `home` and `away` inside `predict_match_probs()` to match the expected signature in the task brief.

4. **Test Exception Swallowing Removal & Empty Fit Assertion**:
   - Updated `scratch/test_dixon_coles_decay.py` to remove the `try/except` block swallowing exceptions during empty fit checks.
   - Added assertions verifying that fitting empty data runs without raising exceptions and correctly populates the fallback params.

5. **Case Insensitivity Support**:
   - Handled case-insensitive input by lowercasing and stripping team names in both `fit()` and `predict_match_probs()`.
   - Added a new unit test `test_case_insensitivity_and_whitespace` to verify correct behavior.

## Updated Test Results
- **Command Run:** `python scratch/test_dixon_coles_decay.py`
- **Output:**
  ```
  ....
  ----------------------------------------------------------------------
  Ran 4 tests in 0.106s

  OK
  ```

