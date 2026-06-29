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