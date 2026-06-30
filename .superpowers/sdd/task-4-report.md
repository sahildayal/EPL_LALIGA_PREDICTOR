# Task 4 Report: Google News Roster Health / Injury RSS Parser

## Implementation Details
We implemented the Google News roster health / injury RSS parser that checks headlines for player names and injury keywords, and added these as features to the ML models.
Specifically:
- Implemented `get_roster_health` in [src/data/scrapers/news.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/data/scrapers/news.py) to query the Google News RSS search endpoint for a team's injury news, extract the titles, and flag players in the team's roster that match injury keywords (e.g. `injury`, `injured`, `out`, `suspended`, `doubtful`, `miss`, `absent`, `hamstring`, `knee`). Roster health is computed as `1.0 - (flagged / 11)` capped at a minimum of `0.5`.
- Updated `FEATURE_NAMES` in [src/data/preprocessor.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/data/preprocessor.py) to append `"HTRosterHealth"`, `"ATRosterHealth"`, `"RosterHealthDiff"`, bringing the total feature count to 31.
- Updated `get_match_features` in [src/data/preprocessor.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/data/preprocessor.py) to calculate the home team and away team roster health values, calculate `health_diff = h_health - a_health`, and append these to the returned feature vector.
- Updated `clean_and_load_dataset` in [src/data/preprocessor.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/data/preprocessor.py) to safely fill NAs with `1.0` for roster health features and `0.0` for the difference feature.
- Adjusted existing tests in [scratch/test_roster_features.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_roster_features.py) and [scratch/test_fatigue_travel.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_fatigue_travel.py) to reflect the new feature vector length of 31 instead of 28.

## Test Results
We ran the unit and integration tests and they all passed successfully.

### Test suite details in [scratch/test_roster_health.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_roster_health.py):
- `test_injury_news_scoring`: Verifies that `get_match_features` returns a feature vector of length 31 and the health values are less than or equal to 1.0.
- `test_get_roster_health_no_injuries`: Mock unit test verifying that if no injury headlines exist, the roster health score is correctly returned as `1.0`.
- `test_get_roster_health_with_injuries`: Mock unit test verifying that when matching players are mentioned in injury headlines, the roster health score is properly penalized.
- `test_get_roster_health_request_failure`: Mock unit test verifying that if the HTTP request fails, the parser gracefully returns `1.0` roster health.

## TDD Evidence
### RED Phase
- **Command Run:** `python scratch/test_roster_health.py`
- **Output:**
  ```
  FAIL: test_injury_news_scoring (__main__.TestRosterHealth.test_injury_news_scoring)
  ----------------------------------------------------------------------
  Traceback (most recent call last):
    File "C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor\scratch\test_roster_health.py", line 11, in test_injury_news_scoring
      self.assertEqual(len(features), 31)
      ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
  AssertionError: 28 != 31
  ```
- **Why Failure Expected:** The roster health features had not yet been added to `FEATURE_NAMES` or calculated in `get_match_features` in `src/data/preprocessor.py`.

### GREEN Phase
- **Command Run:** `python scratch/test_roster_health.py`
- **Output:**
  ```
  Ran 4 tests in 1.593s

  OK
  ```

## Files Changed
- Modified: [src/data/scrapers/news.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/data/scrapers/news.py)
- Modified: [src/data/preprocessor.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/src/data/preprocessor.py)
- Modified: [scratch/test_roster_features.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_roster_features.py)
- Modified: [scratch/test_fatigue_travel.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_fatigue_travel.py)
- Created: [scratch/test_roster_health.py](file:///C:/Users/Bikash/Desktop/CODEBASE/WorldCupPredictor/scratch/test_roster_health.py)

## Self-Review Findings
- **Completeness:** The new RSS scraper correctly identifies player names and injury keywords, adding three robust features to the ML prediction pipeline.
- **Quality:** Safe exception handling and network mocks are implemented to avoid brittle tests.
- **Compatibility:** Feature defaults are configured, and prior test suites are updated to maintain total green test suite compatibility.
