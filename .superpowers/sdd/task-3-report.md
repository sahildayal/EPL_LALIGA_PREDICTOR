# Task 3 Report: Dynamic FBRef Scraper & SQLite Storage

## What Was Implemented
- Integrated SQLite database cache with player statistics scraping and retrieval in `src/data/scrapers/player_stats.py`.
- Enabled caching player statistics inside the `player_statistics` table using `save_player_stats` and retrieving them via `get_player_stats_cache` with a 7-day TTL check.
- Integrated the blending formula (60% country, 40% club) when retrieving player statistics, supporting:
  - Seeded players (`PLAYER_SEEDS` stats blend)
  - Scraped players (`_scrape_fbref_player` blended with position defaults)
  - Fallback position default profiles (e.g., FW default when no match or scraper error is found)
- Created the TDD scratch test suite `scratch/test_player_scraping.py`.

## TDD Evidence

### RED Phase
- **Command Run:** `python scratch/test_player_scraping.py`
- **Failing Output:**
  ```
  .F
  ======================================================================
  FAIL: test_seeded_player (__main__.TestPlayerScraping.test_seeded_player)
  ----------------------------------------------------------------------
  Traceback (most recent call last):
    File "C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor\scratch\test_player_scraping.py", line 10, in test_seeded_player
      self.assertEqual(stats["name"], "kylian mbappe")
      ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  AssertionError: 'Kylian Mbappe' != 'kylian mbappe'
  - Kylian Mbappe
  ? ^      ^
  + kylian mbappe
  ? ^      ^

  ----------------------------------------------------------------------
  Ran 2 tests in 0.544s

  FAILED (failures=1)
  ```
- **Why the Failure Was Expected:**
  - The function `get_player_stats` returned the unnormalized capital name from seeds/input and did not normalize the cached keys or store them into the SQLite database.
  - The player assists and goals blending formula for scraper and fallback cases had not been fully updated to support SQLite caching.

### GREEN Phase
- **Command Run:** `python scratch/test_player_scraping.py`
- **Passing Output:**
  ```
  ..
  ----------------------------------------------------------------------
  Ran 2 tests in 0.360s

  OK
  ```

## What Was Tested and Test Results
All test files under the `scratch` directory were executed and verified successfully.

1. **Player Scraping and Cache Integration tests:**
   - Command: `python scratch/test_player_scraping.py`
   - Result: `2/2 tests passed`

2. **SQLite Database Cache operations tests:**
   - Command: `python scratch/test_db_cache.py`
   - Result: `4/4 tests passed`

3. **Fixtures & Lineups tests:**
   - Command: `python scratch/test_lineups.py`
   - Result: `11/11 tests passed`

4. **Integration tests:**
   - Command: `python scratch/test_integration.py`
   - Result: `All integration tests passed successfully!`

5. **Team Mapping tests:**
   - Command: `python scratch/test_team_mapping.py`
   - Result: `ALL TEAM MAPPING TESTS PASSED SUCCESSFULLY!`

## Files Changed
- `src/data/scrapers/player_stats.py` (Modified)
- `scratch/test_player_scraping.py` (Created)

## Self-Review Findings
- **Completeness:** All steps outlined in Task 3 brief have been completely implemented.
- **Quality:** Code is clear, adheres to established project conventions, and uses absolute/normalized lower-cased player names for caching consistency.
- **Testing:** The new scratch test verified both seeded and scraped player profiles, demonstrating correct blending functionality and database caching behavior.
- **Output:** Pristine (no warnings or compilation issues besides deprecated datetime warnings already present in external files).

## Final Fixes Applied (2026-06-27)

1. **KeyError on `assists_per_90` resolved:**
   - Modified `src/data/scrapers/player_stats.py` to use `scraped.get("assists_per_90", 0.15)` instead of `scraped["assists_per_90"]` to prevent `KeyError` when scraping results are incomplete.

2. **Added `source` key to cached player stats:**
   - Updated `get_player_stats` in `src/data/scrapers/player_stats.py` to append `cached["source"] = "cached_sqlite"` when statistics are returned directly from the local SQLite cache database.

3. **Offline/Mocked Test Suite:**
   - Mocked all network requests in `scratch/test_player_scraping.py` using `unittest.mock.patch("src.data.scrapers.player_stats.requests.get")`.
   - Verified both dynamic scraping simulation (mock data response) and subsequent SQLite cache retrieval in the test suite.
   - Command run: `python scratch/test_player_scraping.py`
   - Test result:
     ```
     ..
     ----------------------------------------------------------------------
     Ran 2 tests in 0.031s

     OK
     ```
