# Task 1 Report: Starting XI Quality Index Feature Engineering

## Status
**DONE**

## Changes Made
- Modified `src/data/preprocessor.py` to:
  - Append `"HTRosterStrength"`, `"ATRosterStrength"`, and `"RosterStrengthDiff"` to `FEATURE_NAMES`.
  - Fetch match lineups dynamically using `get_match_lineups(home_team, away_team)` and look up starting players' composite statistics via `get_player_stats(player)`.
  - Sum the `xg_per_90` statistics of the players in each lineup to compute roster strength.
  - Apply fallback calculations (`h_avg * 1.5` / `a_avg * 1.5`) when roster strength is 0.0 or scraping/lineup lookup fails.
  - Append the computed home roster strength, away roster strength, and roster strength difference to the `features` numpy array.
  - Set default value mappings for the new columns in `clean_and_load_dataset` (setting roster strength to 1.5 and difference to 0.0 if not present).
- Created a new test suite file `scratch/test_roster_features.py` to verify the calculated roster strength features and array size extensions.
- Updated `scratch/test_fatigue_travel.py` to expect 28 features instead of the old 25.

## Commits
- `9272f18` feat: add Starting XI roster strength features

## Verification & Testing
- Ran TDD test suite `scratch/test_roster_features.py` which failed initially (25 != 28) and passed (OK) after preprocessor implementation.
- Ran the full scratch test suite (`python -m unittest discover -s scratch -p "test_*.py"`):
  - 48 tests passed successfully, verifying correctness of features, travel/fatigue integration, Dixon-Coles model optimization, ELO scoring, and paper trading portfolio bot betting flow.
