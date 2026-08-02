"""
Time-decayed Dixon-Coles, fitted per league.

Adapted from the existing DixonColesRegressor, which was already sound in its
core (vectorised likelihood, exponential decay, sum-to-zero attack constraint).
Three things are changed, all of them about honesty at the edges:

1. **Unknown teams no longer return 0.33/0.33/0.34.** A silent uniform fallback
   is how the old system produced identical predictions for Man City-Burnley and
   Real Madrid-Barcelona. Promoted clubs now get an explicit ClubElo-derived
   prior, and a genuinely unresolvable team raises.
2. **Canonical names**, so 'Nott'm Forest' and 'Nottingham Forest' are one team.
3. **A shots variant.** Every free xG feed is blocked, so alongside goals-DC we
   fit the same model to shots on target and convert to a goal expectation.
   Shot counts are less noisy than goals, which matters early in a season.

Both variants feed the out-of-fold blend in Phase 3; neither is trusted alone.
"""
import warnings

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from src.data.canonical_teams import canonical

DEFAULT_HALFLIFE_DAYS = 365.0


class TeamNotFitted(KeyError):
    """Raised when asked to predict a team the model has never seen."""


def _decay_xi(halflife_days: float) -> float:
    return float(np.log(2.0) / halflife_days)


class DixonColes:
    """
    Bivariate Poisson with the Dixon-Coles low-score correction.

        lambda_home = exp(attack_home + defence_away + home_adv)
        lambda_away = exp(attack_away + defence_home)

    Attack is constrained to sum to zero for identifiability; the overall
    scoring level is absorbed by defence.
    """

    def __init__(self, halflife_days: float = DEFAULT_HALFLIFE_DAYS, max_goals: int = 10):
        self.xi = _decay_xi(halflife_days)
        self.max_goals = max_goals
        self.teams = []
        self.index = {}
        self.attack = None
        self.defence = None
        self.home_adv = 0.25
        self.rho = -0.05
        self.scale = 1.0          # multiplies lambda when fitted on shots
        self.is_fitted = False

    # --- likelihood ---------------------------------------------------------

    def _nll(self, params, h_idx, a_idx, x, y, w):
        n = len(self.teams)
        attack = np.append(params[:n - 1], -np.sum(params[:n - 1]))
        defence = params[n - 1:2 * n - 1]
        home_adv, rho = params[2 * n - 1], params[2 * n]

        eta_h = np.clip(attack[h_idx] + defence[a_idx] + home_adv, -10, 10)
        eta_a = np.clip(attack[a_idx] + defence[h_idx], -10, 10)
        lam, mu = np.exp(eta_h), np.exp(eta_a)

        log_h = x * np.log(np.clip(lam, 1e-10, None)) - lam
        log_a = y * np.log(np.clip(mu, 1e-10, None)) - mu

        tau = np.ones_like(lam)
        m00, m01, m10, m11 = (x == 0) & (y == 0), (x == 0) & (y == 1), (x == 1) & (y == 0), (x == 1) & (y == 1)
        tau[m00] = 1.0 - lam[m00] * mu[m00] * rho
        tau[m01] = 1.0 + lam[m01] * rho
        tau[m10] = 1.0 + mu[m10] * rho
        tau[m11] = 1.0 - rho
        tau = np.clip(tau, 1e-10, None)

        return -np.sum(w * (np.log(tau) + log_h + log_a))

    def fit(self, home, away, home_count, away_count, days_ago, scale: float = 1.0):
        """
        Fits on any non-negative count. `scale` converts the fitted count back to
        a goal expectation (1.0 for goals, ~goals-per-SoT for the shots variant).
        """
        home = [canonical(t, strict=False) for t in home]
        away = [canonical(t, strict=False) for t in away]
        x = np.asarray(home_count, dtype=float)
        y = np.asarray(away_count, dtype=float)
        days = np.asarray(days_ago, dtype=float)

        ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(days)
        home = [t for t, k in zip(home, ok) if k]
        away = [t for t, k in zip(away, ok) if k]
        x, y, days = x[ok], y[ok], days[ok]

        self.teams = sorted(set(home) | set(away))
        self.index = {t: i for i, t in enumerate(self.teams)}
        n = len(self.teams)
        if n < 2 or len(x) < n:
            raise ValueError(f"not enough data to fit: {len(x)} matches, {n} teams")

        h_idx = np.array([self.index[t] for t in home])
        a_idx = np.array([self.index[t] for t in away])
        w = np.exp(-self.xi * days)

        p0 = np.concatenate([np.zeros(n - 1), np.full(n, np.log(max(x.mean(), 0.1))), [0.25], [-0.05]])
        bounds = [(-3, 3)] * (n - 1) + [(-3, 3)] * n + [(-0.5, 1.5)] + [(-0.2, 0.2)]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = minimize(self._nll, p0, args=(h_idx, a_idx, x, y, w),
                           method="L-BFGS-B", bounds=bounds,
                           options={"maxiter": 500, "maxfun": 50000})

        p = res.x
        self.attack = np.append(p[:n - 1], -np.sum(p[:n - 1]))
        self.defence = p[n - 1:2 * n - 1]
        self.home_adv = float(p[2 * n - 1])
        self.rho = float(p[2 * n])
        self.scale = float(scale)
        self.is_fitted = True
        self.converged = bool(res.success)
        return self

    # --- prediction ---------------------------------------------------------

    def lambdas(self, home: str, away: str, priors: dict = None) -> tuple:
        """
        Expected goals for both sides.

        `priors` maps an unseen team to (attack, defence) — used for promoted
        clubs. Without one, an unseen team raises rather than silently becoming
        league-average, which is what made the old Elo emit a constant.
        """
        if not self.is_fitted:
            raise TeamNotFitted("model is not fitted")
        h, a = canonical(home, strict=False), canonical(away, strict=False)
        priors = priors or {}

        def params(team):
            if team in self.index:
                i = self.index[team]
                return self.attack[i], self.defence[i]
            if team in priors:
                return priors[team]
            raise TeamNotFitted(
                f"{team!r} was never fitted and has no prior. Supply one (e.g. from "
                "ClubElo) rather than defaulting to league average."
            )

        ah, dh = params(h)
        aa, da = params(a)
        lam = np.exp(np.clip(ah + da + self.home_adv, -10, 10)) * self.scale
        mu = np.exp(np.clip(aa + dh, -10, 10)) * self.scale
        return float(lam), float(mu)

    def score_matrix(self, home: str, away: str, priors: dict = None) -> np.ndarray:
        lam, mu = self.lambdas(home, away, priors)
        k = np.arange(self.max_goals + 1)
        m = np.outer(poisson.pmf(k, lam), poisson.pmf(k, mu))
        # Dixon-Coles low-score correction
        m[0, 0] *= 1.0 - lam * mu * self.rho
        m[0, 1] *= 1.0 + lam * self.rho
        m[1, 0] *= 1.0 + mu * self.rho
        m[1, 1] *= 1.0 - self.rho
        m = np.clip(m, 1e-12, None)
        return m / m.sum()

    def predict_one(self, home: str, away: str, priors: dict = None) -> np.ndarray:
        m = self.score_matrix(home, away, priors)
        return np.array([np.tril(m, -1).sum(), np.trace(m), np.triu(m, 1).sum()])

    def predict_proba(self, pairs, priors: dict = None) -> np.ndarray:
        """(n, 3) H/D/A probabilities for an iterable of (home, away)."""
        return np.vstack([self.predict_one(h, a, priors) for h, a in pairs])

    def market_probs(self, home, away, priors=None) -> dict:
        """Derived markets from the same score matrix, so they stay coherent."""
        m = self.score_matrix(home, away, priors)
        n = m.shape[0]
        totals = np.add.outer(np.arange(n), np.arange(n))
        btts = m[1:, 1:].sum()
        return {
            "home": float(np.tril(m, -1).sum()),
            "draw": float(np.trace(m)),
            "away": float(np.triu(m, 1).sum()),
            "over_1.5": float(m[totals >= 2].sum()),
            "over_2.5": float(m[totals >= 3].sum()),
            "over_3.5": float(m[totals >= 4].sum()),
            "btts_yes": float(btts),
            "btts_no": float(1.0 - btts),
        }


def elo_priors(teams, ratings: dict, attack_spread: float = 0.0016) -> dict:
    """
    Turns ClubElo ratings into (attack, defence) priors for unfitted clubs.

    A promoted side has no top-flight record, but ClubElo rates second-division
    clubs on the same scale, so it arrives with real information instead of a
    guess. Ratings are centred on the supplied group and scaled to a plausible
    attack/defence range; the model corrects it as results arrive.
    """
    known = {t: ratings[t] for t in teams if t in ratings}
    if not known:
        return {}
    centre = float(np.mean(list(known.values())))
    priors = {}
    for t, elo in known.items():
        edge = (elo - centre) * attack_spread
        priors[t] = (edge, -edge)
    return priors
