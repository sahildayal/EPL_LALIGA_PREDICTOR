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
            
            # Use clipping to prevent overflow in exp/power
            eta_h = np.clip(alpha[h_idx] + beta[a_idx] + gamma, -10, 10)
            eta_a = np.clip(alpha[a_idx] + beta[h_idx], -10, 10)
            
            lam = np.exp(eta_h)
            mu = np.exp(eta_a)
            
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
        if df.empty or 'home_team' not in df.columns or 'away_team' not in df.columns:
            self.teams = []
            self.team_indices = {}
            self.params['alphas'] = np.zeros(0)
            self.params['betas'] = np.full(0, -0.1)
            self.params['gamma'] = 0.2
            self.params['rho'] = 0.05
            return
            
        df = df.copy()
        df['home_team'] = df['home_team'].astype(str).str.lower().str.strip()
        df['away_team'] = df['away_team'].astype(str).str.lower().str.strip()
        
        self.teams = sorted(list(set(df['home_team']).union(set(df['away_team']))))
        self.team_indices = {team: idx for idx, team in enumerate(self.teams)}
        n_teams = len(self.teams)
        
        if n_teams <= 1:
            self.params['alphas'] = np.zeros(n_teams)
            self.params['betas'] = np.full(n_teams, -0.1)
            self.params['gamma'] = 0.2
            self.params['rho'] = 0.05
            return
            
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

    def predict_match_probs(self, home, away, max_goals=8):
        if isinstance(home, str):
            home = home.lower().strip()
        if isinstance(away, str):
            away = away.lower().strip()

        if home not in self.team_indices or away not in self.team_indices:
            return 0.33, 0.33, 0.34
        h_idx = self.team_indices[home]
        a_idx = self.team_indices[away]
        
        alpha_h = self.params['alphas'][h_idx]
        beta_h = self.params['betas'][h_idx]
        alpha_a = self.params['alphas'][a_idx]
        beta_a = self.params['betas'][a_idx]
        gamma = self.params['gamma']
        rho = self.params['rho']
        
        eta_h = np.clip(alpha_h + beta_a + gamma, -10, 10)
        eta_a = np.clip(alpha_a + beta_h, -10, 10)
        
        lam = np.exp(eta_h)
        mu = np.exp(eta_a)
        
        prob_matrix = np.zeros((max_goals + 1, max_goals + 1))
        for x in range(max_goals + 1):
            for y in range(max_goals + 1):
                poisson_h = (np.power(lam, x) * np.exp(-lam)) / math.factorial(x)
                poisson_a = (np.power(mu, y) * np.exp(-mu)) / math.factorial(y)
                tau_val = self._tau(x, y, lam, mu, rho)
                if tau_val <= 0:
                    tau_val = 1e-10
                prob_matrix[x, y] = tau_val * poisson_h * poisson_a
                
        p_home = np.sum(np.tril(prob_matrix, -1))
        p_draw = np.sum(np.diag(prob_matrix))
        p_away = np.sum(np.triu(prob_matrix, 1))
        
        total = p_home + p_draw + p_away
        if total <= 0:
            return 0.33, 0.33, 0.34
        return p_home / total, p_draw / total, p_away / total

