# Task 3 Completion Report: Integration in CLI Commands

## Actions Completed
1. **Regex Optimization in `src/data/team_mapping.py`**:
   - Pre-compiled the regex patterns for `ALIASES_SORTED` at the module level under the dictionary `ALIASES_PATTERNS`.
   - Updated `is_team_match` to use `ALIASES_PATTERNS[alias].finditer(txt_norm)` instead of dynamically compiling regex patterns on every invocation.
2. **Integrated Team Normalization into `run_predict` (`main.py`)**:
   - Imported `normalize_team_name` and `is_team_match` from `src.data.team_mapping`.
   - Updated `run_predict(query: str)` to normalize home and away inputs to canonical lowercase forms.
   - Refactored the Kalshi market matching loops (Moneylines, Game Lines, and Player Props) to match using `normalize_team_name` and `is_team_match` instead of simple substring checking (`home in title` or `away in title`).
3. **Integrated Team Normalization into `run_ask` (`main.py`)**:
   - Replicated the same normalization and event/market title matching logic in `run_ask(query: str, user_model: str)`.
   - Cleaned up the market loops for Moneylines, Game Lines, and Player Props to use robust matching.

## Verification Details
- **Tests Execution**:
  - `python scratch/test_team_mapping.py` -> Passed successfully.
  - `python scratch/test_integration.py` -> Passed successfully.
- **CLI Commands Verification**:
  - Verified `python main.py predict "south africa vs south korea"`:
    - The forecast matrix printed South Africa, Draw, and South Korea probabilities successfully.
    - Kalshi Prices (Moneyline, Over 1.5/2.5 Goals, Both Teams to Score) fetched correctly and displayed exact numerical values instead of `N/A`.
    - Predict Portfolio Bot Paper Bets successfully placed.
  - Verified `python main.py ask "south africa vs south korea"`:
    - Pipelines parsed and mapped all odds successfully.
    - Personal bets and recommendations successfully updated.

## Commit Details
- **Message**: `feat: complete end-to-end team normalization integration in CLI commands`
- **Files Modified**:
  - [main.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/main.py)
  - [src/data/team_mapping.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/data/team_mapping.py)
