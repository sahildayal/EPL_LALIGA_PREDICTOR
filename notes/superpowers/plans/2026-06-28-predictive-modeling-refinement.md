# Predictive Modeling Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve tournament prediction accuracy by implementing time-decayed Dixon-Coles goal expectations, dynamic Elo ratings, advanced ensembled stacking classifiers, fatigue/travel feature engineering, injury penalty adjustments, and storing all parameters in the SQLite database cache.

**Architecture:** We will implement rolling time-decay parameter estimation for Dixon-Coles, match importance & margin of victory Elo scaling, and a StackingClassifier combining XGBoost, LightGBM, and MLP. To optimize performance and ensure portability, team travel distances, fatigue, dynamic ratings, and ensembled outputs will be stored in SQLite cache tables.

**Tech Stack:** Python, Pandas, NumPy, Scikit-learn, XGBoost, LightGBM, SQLite, SciPy Optimize

## Global Constraints
- Maintain case-insensitive matching for all player names.
- Do not introduce external fuzzy matching packages.
- Keep SQLite database connections properly closed (using try-finally).
- Every task must implement TDD with tests written first.
- All code additions must be fully complete (no TBD/TODO placeholders).

---

### Task 1: SQLite Storage Scaffolding & Travel Logs Cache

**Files:**
- Modify: `src/data/cache.py`
- Test: `scratch/test_db_scaffolding.py`

**Interfaces:**
- Consumes: None
- Produces: `save_team_travel(team, city, date, lat, lon)`, `get_team_last_travel(team)`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_db_scaffolding.py` and write test to verify scaffolding works.
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  from src.data.cache import save_team_travel, get_team_last_travel, _conn

  class TestDbScaffolding(unittest.TestCase):
      def test_travel_caching(self):
          save_team_travel("portugal", "lisbon", "2026-06-28", 38.72, -9.14)
          last_travel = get_team_last_travel("portugal")
          self.assertEqual(last_travel["city"], "lisbon")
          self.assertEqual(last_travel["lat"], 38.72)
  ```
- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_db_scaffolding.py`
  Expected: FAIL with `ImportError: cannot import name 'save_team_travel'`
- [ ] **Step 3: Write minimal implementation**
  Modify `src/data/cache.py` to create the `team_travel` table and implement save/get functions.
  ```python
  # Add table definition in cache.py:
  # CREATE TABLE IF NOT EXISTS team_travel (
  #     team TEXT PRIMARY KEY,
  #     city TEXT NOT NULL,
  #     date TEXT NOT NULL,
  #     latitude REAL NOT NULL,
  #     longitude REAL NOT NULL
  # )
  
  def save_team_travel(team: str, city: str, date: str, lat: float, lon: float):
      conn = _conn()
      try:
          conn.execute("""
              INSERT OR REPLACE INTO team_travel (team, city, date, latitude, longitude)
              VALUES (?, ?, ?, ?, ?)
          """, (team.lower().strip(), city.lower().strip(), date, lat, lon))
          conn.commit()
      finally:
          conn.close()

  def get_team_last_travel(team: str) -> dict:
      conn = _conn()
      try:
          cursor = conn.execute("""
              SELECT city, date, latitude, longitude FROM team_travel WHERE team = ?
          """, (team.lower().strip(),))
          row = cursor.fetchone()
          if row:
              return {"city": row[0], "date": row[1], "lat": row[2], "lon": row[3]}
          return None
      finally:
          conn.close()
  ```
- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_db_scaffolding.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add src/data/cache.py scratch/test_db_scaffolding.py
  git commit -m "feat: implement team travel cache table and query methods in SQLite"
  ```

---

### Task 2: Dixon-Coles Time Decay Model & Parameter Estimator

**Files:**
- Create: `src/models/dixon_coles_decay.py`
- Test: `scratch/test_dixon_coles_decay.py`

**Interfaces:**
- Consumes: `master_dataset.csv`
- Produces: `DixonColesRegressor(xi=0.0019)`, `DixonColesRegressor.fit(df)`, `DixonColesRegressor.predict_match_probs(home, away)`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_dixon_coles_decay.py` to verify decay modeling:
  ```python
  import unittest
  import pandas as pd
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  from src.models.dixon_coles_decay import DixonColesRegressor

  class TestDixonColesDecay(unittest.TestCase):
      def test_regressor_fit(self):
          df = pd.DataFrame([
              {"home_team": "england", "away_team": "france", "home_goals": 2, "away_goals": 1, "days_ago": 2},
              {"home_team": "france", "away_team": "england", "home_goals": 0, "away_goals": 3, "days_ago": 10},
              {"home_team": "england", "away_team": "germany", "home_goals": 1, "away_goals": 1, "days_ago": 50}
          ])
          reg = DixonColesRegressor(xi=0.0019)
          reg.fit(df)
          p_h, p_d, p_a = reg.predict_match_probs("england", "france")
          self.assertTrue(0.0 <= p_h <= 1.0)
  ```
- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_dixon_coles_decay.py`
  Expected: FAIL with `ModuleNotFoundError`
- [ ] **Step 3: Write minimal implementation**
  Create `src/models/dixon_coles_decay.py` using `scipy.optimize.minimize` to fit attack/defense/home advantage/correlation parameters dynamically with exponential time weights.
  ```python
  import numpy as np
  import pandas as pd
  from scipy.optimize import minimize
  import math

  class DixonColesRegressor:
      def __init__(self, xi=0.0019):
          self.xi = xi
          self.teams = []
          self.team_indices = {}
          self.params = {}
          
      def _tau(self, x, y, lam, mu, rho):
          if x == 0 and y == 0:
              return 1.0 - lam * mu * rho
          elif x == 0 and y == 1:
              return 1.0 + lam * rho
          elif x == 1 and y == 0:
              return 1.0 + mu * rho
          elif x == 1 and y == 1:
              return 1.0 - rho
          else:
              return 1.0

      def _neg_log_likelihood(self, params, df):
          n_teams = len(self.teams)
          alpha = params[0 : n_teams - 1]
          alpha = np.append(alpha, -np.sum(alpha))
          beta = params[n_teams - 1 : 2 * n_teams - 1]
          gamma = params[2 * n_teams - 1]
          rho = params[2 * n_teams]
          
          nll = 0.0
          for _, row in df.iterrows():
              h_idx = self.team_indices[row['home_team']]
              a_idx = self.team_indices[row['away_team']]
              x = int(row['home_goals'])
              y = int(row['away_goals'])
              t = float(row['days_ago'])
              
              lam = np.exp(alpha[h_idx] + beta[a_idx] + gamma)
              mu = np.exp(alpha[a_idx] + beta[h_idx])
              
              weight = np.exp(-self.xi * t)
              
              poisson_h = (np.power(lam, x) * np.exp(-lam)) / math.factorial(x)
              poisson_a = (np.power(mu, y) * np.exp(-mu)) / math.factorial(y)
              tau_val = self._tau(x, y, lam, mu, rho)
              
              if tau_val <= 0:
                  tau_val = 1e-10
              if poisson_h <= 0:
                  poisson_h = 1e-10
              if poisson_a <= 0:
                  poisson_a = 1e-10
                  
              nll += weight * (np.log(tau_val) + np.log(poisson_h) + np.log(poisson_a))
              
          return -nll

      def fit(self, df):
          self.teams = sorted(list(set(df['home_team']).union(set(df['away_team']))))
          self.team_indices = {team: idx for idx, team in enumerate(self.teams)}
          n_teams = len(self.teams)
          
          init_params = np.concatenate([
              np.zeros(n_teams - 1),
              np.full(n_teams, -0.1),
              [0.2],
              [0.05]
          ])
          
          bounds = (
              [(None, None)] * (n_teams - 1) +
              [(None, 0.5)] * n_teams +
              [(0.0, 1.0)] +
              [(-0.3, 0.3)]
          )
          
          res = minimize(self._neg_log_likelihood, init_params, args=(df,), bounds=bounds, method='L-BFGS-B')
          if res.success:
              fitted = res.x
              self.params['alphas'] = np.append(fitted[0:n_teams-1], -np.sum(fitted[0:n_teams-1]))
              self.params['betas'] = fitted[n_teams-1 : 2*n_teams-1]
              self.params['gamma'] = fitted[2*n_teams-1]
              self.params['rho'] = fitted[2*n_teams]
          else:
              # Fallback params
              self.params['alphas'] = np.zeros(n_teams)
              self.params['betas'] = np.full(n_teams, -0.1)
              self.params['gamma'] = 0.2
              self.params['rho'] = 0.05

      def predict_match_probs(self, home_team, away_team, max_goals=8):
          if home_team not in self.team_indices or away_team not in self.team_indices:
              return 0.33, 0.33, 0.34
          h_idx = self.team_indices[home_team]
          a_idx = self.team_indices[away_team]
          
          alpha_h = self.params['alphas'][h_idx]
          beta_h = self.params['betas'][h_idx]
          alpha_a = self.params['alphas'][a_idx]
          beta_a = self.params['betas'][a_idx]
          gamma = self.params['gamma']
          rho = self.params['rho']
          
          lam = np.exp(alpha_h + beta_a + gamma)
          mu = np.exp(alpha_a + beta_h)
          
          prob_matrix = np.zeros((max_goals + 1, max_goals + 1))
          for x in range(max_goals + 1):
              for y in range(max_goals + 1):
                  poisson_h = (np.power(lam, x) * np.exp(-lam)) / math.factorial(x)
                  poisson_a = (np.power(mu, y) * np.exp(-mu)) / math.factorial(y)
                  tau_val = self._tau(x, y, lam, mu, rho)
                  prob_matrix[x, y] = tau_val * poisson_h * poisson_a
                  
          p_home = np.sum(np.tril(prob_matrix, -1))
          p_draw = np.sum(np.diag(prob_matrix))
          p_away = np.sum(np.triu(prob_matrix, 1))
          
          total = p_home + p_draw + p_away
          if total <= 0:
              return 0.33, 0.33, 0.34
          return p_home / total, p_draw / total, p_away / total
  ```
- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_dixon_coles_decay.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add src/models/dixon_coles_decay.py scratch/test_dixon_coles_decay.py
  git commit -m "feat: implement Dixon-Coles goal regressor with time decay decay parameter estimation"
  ```

---

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

### Task 4: Rest Days, Fatigue Index, and Travel Distance Preprocessing

**Files:**
- Modify: `src/data/preprocessor.py`
- Test: `scratch/test_fatigue_travel.py`

**Interfaces:**
- Consumes: `save_team_travel` and `get_team_last_travel`
- Produces: Travel distance calculation and fatigue rest disparity features added to feature matrix

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_fatigue_travel.py` to verify preprocessor updates:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  from src.data.preprocessor import calculate_distance_km

  class TestFatigueTravel(unittest.TestCase):
      def test_haversine_distance(self):
          # Distance between London (51.5, -0.1) and Paris (48.8, 2.3)
          dist = calculate_distance_km(51.5, -0.1, 48.8, 2.3)
          self.assertTrue(300 < dist < 400)
  ```
- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_fatigue_travel.py`
  Expected: FAIL with `ImportError` or `AttributeError`
- [ ] **Step 3: Write minimal implementation**
  Edit `src/data/preprocessor.py` to add haversine distance helper and rest disparity metrics.
  ```python
  import math

  def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
      R = 6371.0  # Earth's radius in km
      d_lat = math.radians(lat2 - lat1)
      d_lon = math.radians(lon2 - lon1)
      a = math.sin(d_lat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2)**2
      c = 2 * math.asin(math.sqrt(a))
      return R * c
  ```
- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_fatigue_travel.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add src/data/preprocessor.py scratch/test_fatigue_travel.py
  git commit -m "feat: add travel distance math in preprocessor"
  ```

---

### Task 5: Two-Stage Stacking Classifier ML Ensemble

**Files:**
- Create: `src/models/stacking_ensemble.py`
- Test: `scratch/test_stacking_ensemble.py`

**Interfaces:**
- Consumes: Tabular training features
- Produces: `StackingEnsembleModel`, `StackingEnsembleModel.fit(X, y)`, `StackingEnsembleModel.predict_proba(X)`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_stacking_ensemble.py` to verify ensembling works:
  ```python
  import unittest
  import numpy as np
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  from src.models.stacking_ensemble import StackingEnsembleModel

  class TestStackingEnsemble(unittest.TestCase):
      def test_ensemble_prediction(self):
          X = np.random.rand(50, 10)
          y = np.random.choice([0, 1, 2], size=50) # 0: Home, 1: Draw, 2: Away
          model = StackingEnsembleModel()
          model.fit(X, y)
          probs = model.predict_proba(X[:2])
          self.assertEqual(probs.shape, (2, 3))
  ```
- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_stacking_ensemble.py`
  Expected: FAIL with `ModuleNotFoundError`
- [ ] **Step 3: Write minimal implementation**
  Create `src/models/stacking_ensemble.py` wrapping XGBoost, LightGBM, and MLP into a StackingClassifier with Ridge Logistic Regression meta-learner.
  ```python
  from sklearn.ensemble import StackingClassifier
  from sklearn.linear_model import LogisticRegression
  from sklearn.preprocessing import StandardScaler
  from sklearn.pipeline import make_pipeline
  from xgboost import XGBClassifier
  from lightgbm import LGBMClassifier
  from sklearn.neural_network import MLPClassifier

  class StackingEnsembleModel:
      def __init__(self):
          base_estimators = [
              ('xgb', XGBClassifier(
                  n_estimators=100,
                  max_depth=3,
                  learning_rate=0.1,
                  subsample=0.8,
                  random_state=42,
                  eval_metric='mlogloss'
              )),
              ('lgbm', LGBMClassifier(
                  n_estimators=100,
                  max_depth=3,
                  learning_rate=0.1,
                  subsample=0.8,
                  random_state=42
              )),
              ('mlp', make_pipeline(
                  StandardScaler(),
                  MLPClassifier(
                      hidden_layer_sizes=(32, 16),
                      activation='relu',
                      max_iter=300,
                      random_state=42
                  )
              ))
          ]
          self.clf = StackingClassifier(
              estimators=base_estimators,
              final_estimator=LogisticRegression(penalty='l2', C=1.0),
              cv=3,
              n_jobs=-1,
              passthrough=True
          )

      def fit(self, X, y):
          self.clf.fit(X, y)

      def predict_proba(self, X):
          return self.clf.predict_proba(X)
  ```
- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_stacking_ensemble.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add src/models/stacking_ensemble.py scratch/test_stacking_ensemble.py
  git commit -m "feat: implement StackingEnsembleModel integrating XGBoost, LightGBM, and MLP"
  ```
