import numpy as np
import pandas as pd
from scipy.optimize import minimize
import math
import warnings

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

    def _neg_log_likelihood(self, params, h_indices, a_indices, x, y, t):
        n_teams = len(self.teams)
        alpha = params[0 : n_teams - 1]
        alpha = np.append(alpha, -np.sum(alpha))
        beta = params[n_teams - 1 : 2 * n_teams - 1]
        gamma = params[2 * n_teams - 1]
        rho = params[2 * n_teams]
        
        eta_h = np.clip(alpha[h_indices] + beta[a_indices] + gamma, -10, 10)
        eta_a = np.clip(alpha[a_indices] + beta[h_indices], -10, 10)
        
        lam = np.exp(eta_h)
        mu = np.exp(eta_a)
        
        weight = np.exp(-self.xi * t)
        
        lam_clipped = np.clip(lam, 1e-10, None)
        mu_clipped = np.clip(mu, 1e-10, None)
        
        # We drop the factorial term since it's constant w.r.t optimization variables
        log_poisson_h = x * np.log(lam_clipped) - lam
        log_poisson_a = y * np.log(mu_clipped) - mu
        
        tau_val = np.ones_like(x, dtype=float)
        
        cond_00 = (x == 0) & (y == 0)
        cond_01 = (x == 0) & (y == 1)
        cond_10 = (x == 1) & (y == 0)
        cond_11 = (x == 1) & (y == 1)
        
        tau_val[cond_00] = 1.0 - lam[cond_00] * mu[cond_00] * rho
        tau_val[cond_01] = 1.0 + lam[cond_01] * rho
        tau_val[cond_10] = 1.0 + mu[cond_10] * rho
        tau_val[cond_11] = 1.0 - rho
        
        tau_val = np.clip(tau_val, 1e-10, None)
        
        nll = -np.sum(weight * (np.log(tau_val) + log_poisson_h + log_poisson_a))
        return nll

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
            
        # Precompute arrays for vectorized neg_log_likelihood to be super fast
        h_indices = np.array([self.team_indices[t] for t in df['home_team']])
        a_indices = np.array([self.team_indices[t] for t in df['away_team']])
        x = df['home_goals'].astype(int).values
        y = df['away_goals'].astype(int).values
        t = df['days_ago'].astype(float).values
        
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
        
        res = minimize(
            self._neg_log_likelihood,
            init_params,
            args=(h_indices, a_indices, x, y, t),
            bounds=bounds,
            method='L-BFGS-B',
            options={'maxfun': 50000, 'maxiter': 500}
        )
        
        fitted = res.x
        self.params['alphas'] = np.append(fitted[0:n_teams-1], -np.sum(fitted[0:n_teams-1]))
        self.params['betas'] = fitted[n_teams-1 : 2*n_teams-1]
        self.params['gamma'] = fitted[2*n_teams-1]
        self.params['rho'] = fitted[2*n_teams]
        
        if not res.success:
            warnings.warn(f"Optimization did not converge fully: {res.message}. Using best available parameters.")

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

