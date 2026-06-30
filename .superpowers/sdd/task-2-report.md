# Task 2 Report: Confederation ELO Calibration

## Implementation Details
We implemented ELO ratings differential boosting based on team confederations (UEFA, CONMEBOL, AFC, CAF, CONCACAF, OFC) to calibrate match prediction models.
Specifically:
- Defined the confederation mappings `TEAM_CONFEDERATION` and their corresponding ELO boosts/penalties `CONFEDERATION_BOOST` in `src/predictor.py`.
- Updated `predict_match` to retrieve each team's confederation (defaulting to `"uefa"` if unknown) and calculate their boosts.
- Modified the rating difference calculation to apply these boosts, i.e., `elo_diff = (h_elo + h_boost) - (a_elo + a_boost)`, rounded to 1 decimal place.
- Ensured the adjusted ELO ratings are correctly fed into the ELO probability prediction inside `predict_match` by constructing a localized `EloModel` instance to run `.predict()`.

## Test Results
We ran the unit tests under `scratch/test_confederation_calibration.py` and the calibration test passed successfully.

### Test suite details:
- `test_confederation_boosting`: Sets explicit baseline Elo ratings for Brazil (CONMEBOL, +50 boost) and Japan (AFC, -20 penalty) so that the initial difference is exactly `162.1`, then verifies that after applying calibration, the reported ELO ratings difference is exactly `232.1` (a `+70` rating points shift).

## TDD Evidence
### RED Phase
- **Command Run:** `python scratch/test_confederation_calibration.py`
- **Output:**
  ```
  F
  ======================================================================
  FAIL: test_confederation_boosting (__main__.TestConfedCalibration.test_confederation_boosting)
  ----------------------------------------------------------------------
  Traceback (most recent call last):
    File "C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor\scratch\test_confederation_calibration.py", line 16, in test_confederation_boosting
      self.assertEqual(res.elo_diff, 232.1) # rating diff (162.1) + confed diff (70.0)
      ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^
  AssertionError: 162.0999999999999 != 232.1

  ----------------------------------------------------------------------
  Ran 1 test in 2.082s

  FAILED (failures=1)
  ```
- **Why Failure Expected:** The predictor had not yet implemented confederation boosts, so `elo_diff` was the uncalibrated raw difference `162.1`.

### GREEN Phase
- **Command Run:** `python scratch/test_confederation_calibration.py`
- **Output:**
  ```
  .
  ----------------------------------------------------------------------
  Ran 1 test in 2.093s

  OK
  ```

## Files Changed
- Modified: [src/predictor.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/predictor.py)
- Created: [scratch/test_confederation_calibration.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_confederation_calibration.py)

## Self-Review Findings
- **Completeness:** The implementation covers both `elo_diff` rating difference adjustment and ELO probability prediction adjustment inside `predict_match`.
- **Quality:** Safe dictionaries and fallback defaults ensure unknown national teams default to UEFA parameters with 0.0 boost adjustment without crashing.
- **Testing:** The test explicitly controls team ELOs to verify mathematical correctness of the confederation delta (+70 points shift) precisely.
