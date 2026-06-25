import math
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson


def win_probability(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10, (elo_b - elo_a) / 400.0))


def _estimate_draw_prob(elo_a: float, elo_b: float) -> float:
    elo_diff = abs(elo_a - elo_b)
    draw = 0.28 * math.exp(-elo_diff / 600)
    return round(max(0.08, min(0.32, draw)), 4)


class EloModel:
    """
    Elo-based prediction system.
    """
    def __init__(self, default_elo: float = 1700.0):
        self.default_elo = default_elo
        self.ratings = {}

    def get(self, team: str) -> float:
        return self.ratings.get(team.lower().strip(), self.default_elo)

    def set(self, team: str, elo: float):
        self.ratings[team.lower().strip()] = elo

    def update(self, team_a: str, team_b: str, result: float, k: float = 32.0):
        """
        result: 1.0 = team_a won, 0.5 = draw, 0.0 = team_b won.
        """
        elo_a = self.get(team_a)
        elo_b = self.get(team_b)
        exp_a = win_probability(elo_a, elo_b)
        exp_b = 1.0 - exp_a

        new_a = elo_a + k * (result - exp_a)
        new_b = elo_b + ((1 - result) - exp_b) * k

        self.set(team_a, round(new_a, 2))
        self.set(team_b, round(new_b, 2))

    def predict(self, team_a: str, team_b: str, home_advantage: float = 0.0) -> dict:
        elo_a = self.get(team_a) + home_advantage
        elo_b = self.get(team_b)

        p_a = win_probability(elo_a, elo_b)
        draw_prob = _estimate_draw_prob(elo_a - home_advantage, elo_b)

        p_a_adj = p_a * (1 - draw_prob)
        p_b_adj = (1.0 - p_a) * (1 - draw_prob)

        return {
            "home_win": round(p_a_adj, 4),
            "draw": round(draw_prob, 4),
            "away_win": round(p_b_adj, 4),
        }


def _tau(x: int, y: int, lam_h: float, lam_a: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lam_h * lam_a * rho
    elif x == 1 and y == 0:
        return 1 + lam_a * rho
    elif x == 0 and y == 1:
        return 1 + lam_h * rho
    elif x == 1 and y == 1:
        return 1 - rho
    return 1.0


def _score_probability(score_home: int, score_away: int, lam_home: float, lam_away: float, rho: float) -> float:
    tau = _tau(score_home, score_away, lam_home, lam_away, rho)
    p = tau * poisson.pmf(score_home, lam_home) * poisson.pmf(score_away, lam_away)
    return max(p, 1e-10)


class DixonColesModel:
    """
    Dixon-Coles bivariate Poisson model.
    """
    HOME_ADVANTAGE = 0.25

    def __init__(self):
        self.attack = {}
        self.defense = {}
        self.rho = -0.13
        self.is_fitted = False

    def fit(self, matches: list):
        """
        matches: list of dicts with {"home_team", "away_team", "home_goals", "away_goals"}
        """
        teams = sorted(list(set(
            [m["home_team"] for m in matches] + [m["away_team"] for m in matches]
        )))
        n = len(teams)
        if n == 0:
            return

        def neg_log_likelihood(params):
            attack = {t: params[i] for i, t in enumerate(teams)}
            defense = {t: params[n + i] for i, t in enumerate(teams)}
            rho = params[2 * n]

            ll = 0.0
            for m in matches:
                ht, at = m["home_team"], m["away_team"]
                hg, ag = int(m["home_goals"]), int(m["away_goals"])

                lam_h = math.exp(attack[ht] + defense[at] + self.HOME_ADVANTAGE)
                lam_a = math.exp(attack[at] + defense[ht])
                lam_h = max(lam_h, 0.01)
                lam_a = max(lam_a, 0.01)

                tau = _tau(hg, ag, lam_h, lam_a, rho)
                if tau <= 0:
                    tau = 1e-8

                ll += (
                    math.log(tau)
                    + hg * math.log(lam_h) - lam_h - sum(math.log(i) for i in range(1, hg + 1))
                    + ag * math.log(lam_a) - lam_a - sum(math.log(i) for i in range(1, ag + 1))
                )
            return -ll

        x0 = np.zeros(2 * n + 1)
        x0[-1] = -0.13
        constraints = [{"type": "eq", "fun": lambda p: sum(p[:n])}]

        try:
            res = minimize(
                neg_log_likelihood,
                x0,
                method="SLSQP",
                constraints=constraints,
                bounds=[(None, None)] * (2 * n) + [(-0.5, 0.5)],
                options={"maxiter": 150},
            )
            params = res.x
        except Exception:
            params = x0

        for i, t in enumerate(teams):
            self.attack[t] = float(params[i])
            self.defense[t] = float(params[n + i])
        self.rho = float(params[2 * n])
        self.is_fitted = True

    def get_lambdas(self, home_team: str, away_team: str, neutral: bool = False) -> tuple:
        ha = self.attack.get(home_team, 0.0)
        hd = self.defense.get(home_team, 0.0)
        aa = self.attack.get(away_team, 0.0)
        ad = self.defense.get(away_team, 0.0)

        home_adv = 0.0 if neutral else self.HOME_ADVANTAGE
        lam_home = math.exp(ha + ad + home_adv)
        lam_away = math.exp(aa + hd)
        return max(lam_home, 0.1), max(lam_away, 0.1)

    def predict_score_matrix(self, home_team: str, away_team: str, max_goals: int = 6, neutral: bool = False) -> np.ndarray:
        max_goals = int(max_goals)
        lam_h, lam_a = self.get_lambdas(home_team, away_team, neutral)
        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                matrix[h, a] = _score_probability(h, a, lam_h, lam_a, self.rho)
        return matrix / matrix.sum()

    def predict(self, home_team: str, away_team: str, neutral: bool = False) -> dict:
        matrix = self.predict_score_matrix(home_team, away_team, max_goals=8, neutral=neutral)
        home_win = 0.0
        draw = 0.0
        away_win = 0.0

        for h in range(matrix.shape[0]):
            for a in range(matrix.shape[1]):
                p = matrix[h, a]
                if h > a:
                    home_win += p
                elif h == a:
                    draw += p
                else:
                    away_win += p

        return {
            "home_win": round(home_win, 4),
            "draw": round(draw, 4),
            "away_win": round(away_win, 4),
        }
