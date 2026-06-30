### Task 1: Starting XI Quality Index Feature Engineering

**Files:**
- Modify: `src/data/preprocessor.py`
- Test: `scratch/test_roster_features.py`

**Interfaces:**
- Consumes: Lineup rosters from `src/data/scrapers/fixtures.py` and player stats from `src/data/scrapers/player_stats.py`
- Produces: Features array extended by three columns (`HTRosterStrength`, `ATRosterStrength`, `RosterStrengthDiff`)

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_roster_features.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  
  class TestRosterFeatures(unittest.TestCase):
      def test_roster_strength_calculations(self):
          from src.data.preprocessor import get_match_features
          features = get_match_features("brazil", "japan")
          # Verify extended feature length is 28 (original 25 + 3 new features)
          self.assertEqual(len(features), 28)
          self.assertTrue(features[25] > 0.0) # HTRosterStrength
          self.assertTrue(features[26] > 0.0) # ATRosterStrength
  
  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_roster_features.py`
  Expected: FAIL with `AssertionError: 25 != 28`

- [ ] **Step 3: Modify preprocessor code**
  Update `FEATURE_NAMES` and `get_match_features` in `src/data/preprocessor.py` to append the new roster columns:
  ```python
  # In src/data/preprocessor.py lines 10-20:
  FEATURE_NAMES = [
      "B365H", "B365D", "B365A",
      "HTGS", "HTGC", "HTP", "HTGD",
      "ATGS", "ATGC", "ATP", "ATGD",
      "HTFormPts", "ATFormPts",
      "DiffFormPts", "DiffPts", "DiffGD",
      "SentimentScore",
      "HTRestDays", "ATRestDays", "RestDisparity",
      "HTExtremeFatigue", "ATExtremeFatigue",
      "HTTravel", "ATTravel", "TravelDisparity",
      "HTRosterStrength", "ATRosterStrength", "RosterStrengthDiff"
  ]
  ```
  In `get_match_features` (around line 178):
  ```python
      try:
          from src.data.scrapers.fixtures import get_match_lineups
          from src.data.scrapers.player_stats import get_player_stats
          lineups_res = get_match_lineups(home_team, away_team)
          h_lineup = lineups_res.get("home_lineup", [])
          a_lineup = lineups_res.get("away_lineup", [])
          
          h_roster_strength = sum([get_player_stats(p).get("xg_per_90", 0.1) for p in h_lineup])
          a_roster_strength = sum([get_player_stats(p).get("xg_per_90", 0.1) for p in a_lineup])
      except Exception:
          h_roster_strength, a_roster_strength = 0.0, 0.0
          
      if h_roster_strength == 0.0:
          h_roster_strength = h_avg * 1.5
      if a_roster_strength == 0.0:
          a_roster_strength = a_avg * 1.5
          
      roster_strength_diff = h_roster_strength - a_roster_strength
  ```
  Add these parameters to the returned `features` array.
  Update `clean_and_load_dataset` default mappings:
  ```python
              elif "RosterStrength" in col:
                  df[col] = 1.5 if "Diff" not in col else 0.0
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_roster_features.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/data/preprocessor.py scratch/test_roster_features.py
  git commit -m "feat: add Starting XI roster strength features"
  ```

---
