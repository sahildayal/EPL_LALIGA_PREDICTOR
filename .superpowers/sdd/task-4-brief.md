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
