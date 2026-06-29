### Task 3: Advanced Elo Rating System & Margin of Victory Multiplier

**Files:**
- Create: `src/models/advanced_elo.py`
- Test: `scratch/test_advanced_elo.py`

**Interfaces:**
- Consumes: Elo rating difference
- Produces: `EloSystem`, `EloSystem.update_ratings(home, away, home_goals, away_goals, k_factor, is_neutral)`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_advanced_elo.py` to verify rating updates:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  from src.models.advanced_elo import EloSystem

  class TestAdvancedElo(unittest.TestCase):
      def test_elo_update(self):
          system = EloSystem(default_rating=1600, H=100)
          # Portugal defeats Spain 3-0 on neutral ground with World Cup Knockout K-factor (60)
          new_h, new_a = system.update_ratings("portugal", "spain", 3, 0, k_factor=60, is_neutral=True)
          self.assertTrue(new_h > 1600)
          self.assertTrue(new_a < 1600)
  ```
- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_advanced_elo.py`
  Expected: FAIL with `ModuleNotFoundError`
- [ ] **Step 3: Write minimal implementation**
  Create `src/models/advanced_elo.py` to calculate margin-of-victory scaled Elo updates.
  ```python
  import numpy as np

  class EloSystem:
      def __init__(self, default_rating=1500, H=100):
          self.ratings = {}
          self.default_rating = default_rating
          self.H = H

      def get_rating(self, team):
          return self.ratings.get(team.lower().strip(), self.default_rating)

      def calculate_win_expectancy(self, team_rating, opp_rating, is_home=False):
          dr = team_rating - opp_rating
          if is_home:
              dr += self.H
          return 1.0 / (10 ** (-dr / 400.0) + 1.0)

      def _get_gd_multiplier(self, goal_diff):
          N = abs(goal_diff)
          if N <= 1:
              return 1.0
          elif N == 2:
              return 1.5
          elif N == 3:
              return 1.75
          else:
              return 1.75 + (N - 3) / 8.0

      def update_ratings(self, home_team, away_team, home_goals, away_goals, k_factor, is_neutral=False):
          h_key = home_team.lower().strip()
          a_key = away_team.lower().strip()
          
          r_home = self.get_rating(h_key)
          r_away = self.get_rating(a_key)
          
          we_home = self.calculate_win_expectancy(r_home, r_away, is_home=(not is_neutral))
          we_away = 1.0 - we_home
          
          if home_goals > away_goals:
              w_home, w_away = 1.0, 0.0
          elif home_goals < away_goals:
              w_home, w_away = 0.0, 1.0
          else:
              w_home, w_away = 0.5, 0.5
              
          gd_mult = self._get_gd_multiplier(home_goals - away_goals)
          
          r_home_new = r_home + k_factor * gd_mult * (w_home - we_home)
          r_away_new = r_away + k_factor * gd_mult * (w_away - we_away)
          
          self.ratings[h_key] = round(r_home_new, 1)
          self.ratings[a_key] = round(r_away_new, 1)
          
          return r_home_new, r_away_new
  ```
- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_advanced_elo.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add src/models/advanced_elo.py scratch/test_advanced_elo.py
  git commit -m "feat: implement advanced Elo calculator with K-factor importance and margin of victory multipliers"
  ```

---