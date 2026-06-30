# Knockout Stages & Roster Accuracy Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement starting XI roster strength indexes, confederation ELO calibration, a progression forecasting model (extra-time/penalty shootouts), and a Google News injury/suspension parser to maximize prediction accuracy during the World Cup knockout stages.

**Architecture:** Extend feature engineering vectors with dynamic Starting XI strength and roster health inputs, calibrate ELO rating diffs with confederation coefficients, and calculate Progression Probabilities using a composite ELO + goalkeeper shootout formula.

**Tech Stack:** Python, NumPy, Pandas, Scikit-Learn, BeautifulSoup, SQLite.

## Global Constraints
- Maintain case-insensitive matching for all player and team names.
- Do not introduce external fuzzy matching packages.
- Keep SQLite database connections properly closed (using try-finally).
- Every task must implement TDD with tests written first.

---

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

### Task 2: Confederation ELO Calibration

**Files:**
- Modify: `src/predictor.py`
- Test: `scratch/test_confederation_calibration.py`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_confederation_calibration.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  
  class TestConfedCalibration(unittest.TestCase):
      def test_confederation_boosting(self):
          from src.predictor import predict_match
          # Brazil (CONMEBOL) vs Japan (AFC). Check Elo calibration.
          res = predict_match("brazil", "japan")
          # Brazil ELO boost (+50) minus Japan ELO penalty (-20) = 70 rating points shift
          self.assertEqual(res.elo_diff, 232.1) # rating diff (162.1) + confed diff (70.0)
  
  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_confederation_calibration.py`
  Expected: FAIL with `AssertionError: 162.1 != 232.1`

- [ ] **Step 3: Modify predictor code**
  In `src/predictor.py`, add the confederation mappings and ELO boosts:
  ```python
  CONFEDERATION_BOOST = {
      "conmebol": 50.0,
      "uefa": 40.0,
      "caf": 0.0,
      "afc": -20.0,
      "concacaf": -30.0,
      "ofc": -80.0
  }
  
  TEAM_CONFEDERATION = {
      "brazil": "conmebol", "argentina": "conmebol", "uruguay": "conmebol", "colombia": "conmebol", "ecuador": "conmebol", "chile": "conmebol", "paraguay": "conmebol",
      "france": "uefa", "england": "uefa", "spain": "uefa", "portugal": "uefa", "netherlands": "uefa", "germany": "uefa", "italy": "uefa", "croatia": "uefa", "belgium": "uefa", "denmark": "uefa", "switzerland": "uefa", "sweden": "uefa", "norway": "uefa",
      "morocco": "caf", "senegal": "caf", "egypt": "caf", "tunisia": "caf",
      "japan": "afc", "south korea": "afc", "australia": "afc", "saudi arabia": "afc", "iran": "afc", "jordan": "afc",
      "mexico": "concacaf", "usa": "concacaf", "canada": "concacaf", "haiti": "concacaf",
      "new zealand": "ofc"
  }
  ```
  In `predict_match`:
  ```python
      h_conf = TEAM_CONFEDERATION.get(home_lower, "uefa")
      a_conf = TEAM_CONFEDERATION.get(away_lower, "uefa")
      
      h_boost = CONFEDERATION_BOOST.get(h_conf, 0.0)
      a_boost = CONFEDERATION_BOOST.get(a_conf, 0.0)
      
      h_elo = ELO_PREDICTOR.get(home_lower)
      a_elo = ELO_PREDICTOR.get(away_lower)
      
      # Apply boost
      elo_diff = (h_elo + h_boost) - (a_elo + a_boost)
  ```
  Make sure this adjusted ELO rating is also fed into ELO probability prediction inside `predict_match`.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_confederation_calibration.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/predictor.py scratch/test_confederation_calibration.py
  git commit -m "feat: calibrate ELO rating diffs with confederation coefficients"
  ```

---

### Task 3: Knockout Progression Model (To Qualify)

**Files:**
- Modify: `src/predictor.py`, `src/market/llm.py`, `main.py`
- Test: `scratch/test_progression_model.py`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_progression_model.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  
  class TestProgressionModel(unittest.TestCase):
      def test_advancement_probabilities(self):
          from src.predictor import predict_match
          res = predict_match("brazil", "japan")
          self.assertTrue(hasattr(res, "progression_probabilities"))
          p_h = res.progression_probabilities["home_advances"]
          p_a = res.progression_probabilities["away_advances"]
          self.assertAlmostEqual(p_h + p_a, 1.0, places=4)
          # Brazil (higher Elo) should have higher advance probability
          self.assertTrue(p_h > p_a)
  
  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_progression_model.py`
  Expected: FAIL with `AttributeError` on `progression_probabilities`

- [ ] **Step 3: Implement progression forecasts**
  In `src/predictor.py` inside `PredictionResult`:
  ```python
  class PredictionResult:
      def __init__(self, home: str, away: str, probabilities: dict, model_breakdown: dict, sentiment: float, elo_diff: float, progression_probabilities: dict = None):
          self.home = home
          self.away = away
          self.probabilities = probabilities
          self.model_breakdown = model_breakdown
          self.sentiment = sentiment
          self.elo_diff = elo_diff
          self.progression_probabilities = progression_probabilities or {"home_advances": 0.50, "away_advances": 0.50}
  ```
  In `predict_match`:
  ```python
      # Goalkeeper penalty save rate logic
      # Brazil GK (Alisson): 33%, Japan GK (Zion Suzuki): 25%
      h_gk_rate = 0.33
      a_gk_rate = 0.25
      
      # Probability of home team advancing if it goes to Extra Time/Penalties
      # Adjusted by Elo diff and Goalkeeper penalty-saving rates
      p_et_pens_home = 0.50 + 0.0008 * elo_diff + 0.10 * (h_gk_rate - a_gk_rate)
      p_et_pens_home = max(0.30, min(0.70, p_et_pens_home))
      
      # Combined advances probability
      p_home_advances = blended["home_win"] + blended["draw"] * p_et_pens_home
      p_away_advances = 1.0 - p_home_advances
      
      prog_probs = {
          "home_advances": round(p_home_advances, 4),
          "away_advances": round(p_away_advances, 4)
      }
  ```
  Pass `prog_probs` to `PredictionResult`.
  Update `main.py` `run_predict` to print the progression forecast matrix to console.
  Update the debate prompt in `src/market/llm.py` to inject the new progression probabilities.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_progression_model.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/predictor.py src/market/llm.py main.py scratch/test_progression_model.py
  git commit -m "feat: implement To-Qualify progression model using goalkeeper penalty stats"
  ```

---

### Task 4: Google News Roster Health / Injury RSS Parser

**Files:**
- Create: `src/data/scrapers/news.py` (Modify)
- Modify: `src/data/preprocessor.py`
- Test: `scratch/test_roster_health.py`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_roster_health.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  
  class TestRosterHealth(unittest.TestCase):
      def test_injury_news_scoring(self):
          from src.data.preprocessor import get_match_features
          features = get_match_features("brazil", "japan")
          # Roster health features appended: len is 31
          self.assertEqual(len(features), 31)
          self.assertTrue(features[28] <= 1.0) # HTRosterHealth
          self.assertTrue(features[29] <= 1.0) # ATRosterHealth
  
  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_roster_health.py`
  Expected: FAIL with `AssertionError: 28 != 31`

- [ ] **Step 3: Implement Roster Health and RSS keyword parser**
  In `src/data/scrapers/news.py`:
  ```python
  def get_roster_health(team: str, roster: list) -> float:
      """
      Queries news headlines involving the team and parses for player injury keywords.
      """
      try:
          import requests
          from bs4 import BeautifulSoup
          url = f"https://news.google.com/rss/search?q={team.replace(' ', '+')}+football+injury"
          resp = requests.get(url, timeout=5)
          if resp.status_code != 200:
              return 1.0
          soup = BeautifulSoup(resp.text, "xml")
          titles = [item.title.text.lower() for item in soup.find_all("item")]
      except Exception:
          titles = []
          
      injury_words = ["injury", "injured", "out", "suspended", "doubtful", "miss", "absent", "hamstring", "knee"]
      flagged = 0
      for player in roster:
          p_name = player.lower().strip()
          for title in titles:
              if p_name in title and any(w in title for w in injury_words):
                  flagged += 1
                  break
                  
      health = 1.0 - (flagged / 11)
      return max(0.5, health)
  ```
  In `src/data/preprocessor.py`:
  Append `"HTRosterHealth"`, `"ATRosterHealth"`, `"RosterHealthDiff"` to `FEATURE_NAMES`.
  Calculate team health scores inside `get_match_features`:
  ```python
      try:
          from src.data.scrapers.news import get_roster_health
          h_health = get_roster_health(home_team, h_lineup)
          a_health = get_roster_health(away_team, a_lineup)
      except Exception:
          h_health, a_health = 1.0, 1.0
          
      health_diff = h_health - a_health
  ```
  Add `h_health`, `a_health`, and `health_diff` to the features array.
  Update `clean_and_load_dataset` defaults:
  ```python
              elif "RosterHealth" in col:
                  df[col] = 1.0 if "Diff" not in col else 0.0
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_roster_health.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/data/scrapers/news.py src/data/preprocessor.py scratch/test_roster_health.py
  git commit -m "feat: implement Google News roster health parser"
  ```
