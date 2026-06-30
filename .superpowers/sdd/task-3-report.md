# Task 3 Report: Knockout Progression Model (To Qualify)

## Implementation Details
We implemented match progression / To-Qualify forecast logic to calculate the probability of each team advancing to the next round of a knockout match (accounting for extra time and penalty shootouts), updated the scout/quant LLM debate prompts with these details, and outputted a progression forecast table in the `predict` CLI command.
Specifically:
- Updated the `PredictionResult` class in `src/predictor.py` to accept and store `progression_probabilities` (defaulting to equal 50/50 split if none provided).
- Implemented goalkeeper-influenced advancement calculations in `predict_match` in `src/predictor.py` using a goalkeeper penalty save rate dictionary mapping (`brazil` -> 33%, `japan` -> 25%, defaulting to 28% for others).
- Computed progression probability as: `p_home_advances = blended_home_win + blended_draw * p_et_pens_home`, where `p_et_pens_home` represents the home team's chances if the match is decided in Extra Time/Penalties (modeled as `0.50 + 0.0008 * elo_diff + 0.10 * (h_gk_rate - a_gk_rate)` capped between `0.30` and `0.70`).
- Updated `main.py` `run_predict` to print the To-Qualify progression forecast table to the console using a Rich `Table`.
- Updated the Gemini debate generation prompt in `src/market/llm.py` to accept and inject `progression_probs` as a Match Data point.
- Updated the debate execution call in `main.py` `run_ask` to pass `progression_probs` to the LLM agent.

## Test Results
We ran the unit tests under `scratch/test_progression_model.py` and the progression tests passed successfully.

### Test suite details:
- `test_advancement_probabilities_brazil_japan`: Verifies Brazil (higher Elo, Alisson) vs Japan (Zion Suzuki) calculates a proper progression forecast where Brazil has a significantly higher progression probability (>70%), and the probabilities sum to 1.0.
- `test_advancement_probabilities_japan_brazil`: Verifies that reversing the home/away assignment still results in the stronger team (Brazil) being favored to advance.
- `test_default_goalkeeper_rates`: Verifies that matches between teams not explicitly in the goalie save rate dictionary (e.g. France vs England) run successfully and probabilities sum to 1.0.

## TDD Evidence
### RED Phase
- **Command Run:** `python scratch/test_progression_model.py`
- **Output:**
  ```
  F
  ======================================================================
  FAIL: test_advancement_probabilities (__main__.TestProgressionModel.test_advancement_probabilities)
  ----------------------------------------------------------------------
  Traceback (most recent call last):
    File "C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor\scratch\test_progression_model.py", line 10, in test_advancement_probabilities
      self.assertTrue(hasattr(res, "progression_probabilities"))
      ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  AssertionError: False is not true

  ----------------------------------------------------------------------
  Ran 1 test in 2.129s

  FAILED (failures=1)
  ```
- **Why Failure Expected:** The predictor result had not yet implemented the `progression_probabilities` attribute or calculation logic.

### GREEN Phase
- **Command Run:** `python scratch/test_progression_model.py`
- **Output:**
  ```
  ...
  ----------------------------------------------------------------------
  Ran 3 tests in 11.006s

  OK
  ```

## Files Changed
- Modified: [src/predictor.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/predictor.py)
- Modified: [src/market/llm.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/market/llm.py)
- Modified: [main.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/main.py)
- Created: [scratch/test_progression_model.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_progression_model.py)

## Self-Review Findings
- **Completeness:** Knockout progression calculations are successfully integrated into the predictor, the console output, and the LLM debate prompt.
- **Quality:** Safe bounds checking is applied to ensure progression probabilities remain valid. The goalkeeper rate dictionary safely defaults for other teams.
- **Testing:** Unit tests explicitly assert progression probability bounds, reversed configurations, and default team configurations.
