"""
Recovers goal expectations from sharp prices, then prices derived markets.

The Odds API's bulk endpoint serves 1X2 and totals but not BTTS, so BTTS has no
direct sharp line. Rather than fall back on our own model — which walk-forward CV
showed is measurably worse than the market — we solve for the (lambda_home,
lambda_away) pair whose Dixon-Coles scoreline distribution best reproduces the
sharp 1X2 and totals prices, and read BTTS off that distribution.

This is interpolation, not prediction. Every number that comes out is anchored to
prices the market has already set; we are only filling in a derivative the feed
does not publish. That is a legitimate use of a model that cannot beat the market
outright.
"""
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10
DEFAULT_RHO = -0.05


def score_matrix(lam_home: float, lam_away: float, rho: float = DEFAULT_RHO,
                 max_goals: int = MAX_GOALS) -> np.ndarray:
    """Dixon-Coles adjusted bivariate Poisson scoreline distribution."""
    k = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(k, lam_home), poisson.pmf(k, lam_away))
    m[0, 0] *= 1.0 - lam_home * lam_away * rho
    m[0, 1] *= 1.0 + lam_home * rho
    m[1, 0] *= 1.0 + lam_away * rho
    m[1, 1] *= 1.0 - rho
    m = np.clip(m, 1e-15, None)
    return m / m.sum()


def over_probability(m: np.ndarray, line: float) -> float:
    """
    P(total goals beats `line`) for any line a bookmaker actually posts.

    Three cases, and getting them wrong silently corrupts everything downstream:

    * **Half lines** (2.5): plain P(T >= 3).
    * **Integer lines** (3.0): exactly 3 goals is a PUSH — stake refunded. The
      de-vigged over/under pair sums to 1, so those quotes are conditional on no
      push, and we must condition too: P(T > 3) / (1 - P(T = 3)).
    * **Quarter lines** (2.75): the stake is split half at 2.5 and half at 3.0,
      so the effective probability is the average of the two.

    An earlier version handled only half lines and silently dropped the totals
    constraint for anything else, leaving the goal level unidentified while still
    returning a confident-looking BTTS.
    """
    n = m.shape[0]
    totals = np.add.outer(np.arange(n), np.arange(n))

    def half(l):
        return float(m[totals > l].sum())

    def integer(l):
        push = float(m[totals == int(l)].sum())
        over = float(m[totals > l].sum())
        return over / (1.0 - push) if push < 1.0 else 0.0

    frac = round(line % 1, 2)
    if frac == 0.5:
        return half(line)
    if frac == 0.0:
        return integer(line)
    if frac == 0.25:                       # e.g. 2.25 -> half of 2.0 and 2.5
        return 0.5 * integer(line - 0.25) + 0.5 * half(line + 0.25)
    if frac == 0.75:                       # e.g. 2.75 -> half of 2.5 and 3.0
        return 0.5 * half(line - 0.25) + 0.5 * integer(line + 0.25)
    raise ValueError(f"unsupported totals line {line!r}")


def markets_from_matrix(m: np.ndarray) -> dict:
    """Every derived market, read off one scoreline matrix so they stay coherent."""
    n = m.shape[0]
    totals = np.add.outer(np.arange(n), np.arange(n))
    return {
        "home": float(np.tril(m, -1).sum()),
        "draw": float(np.trace(m)),
        "away": float(np.triu(m, 1).sum()),
        "over_0.5": float(m[totals >= 1].sum()),
        "over_1.5": float(m[totals >= 2].sum()),
        "over_2.5": float(m[totals >= 3].sum()),
        "over_3.5": float(m[totals >= 4].sum()),
        "btts_yes": float(m[1:, 1:].sum()),
        "btts_no": float(1.0 - m[1:, 1:].sum()),
    }


def solve_lambdas(fair_1x2: dict, fair_totals: dict = None, totals_line: float = 2.5,
                  rho: float = DEFAULT_RHO) -> tuple:
    """
    Finds (lambda_home, lambda_away) reproducing the supplied sharp probabilities.

    `fair_1x2` needs home/draw/away; `fair_totals` optionally supplies the over
    probability at `totals_line`. Both are de-vigged probabilities.

    Returns (lam_home, lam_away, diagnostics). The caller should check
    diagnostics['max_error'] before trusting derived markets — a poor fit means
    the sharp prices are not consistent with any single bivariate Poisson, and
    silently pricing BTTS off a bad fit is exactly the sort of quiet error this
    rebuild exists to remove.
    """
    for k in ("home", "draw", "away"):
        if k not in fair_1x2:
            raise ValueError(f"fair_1x2 missing {k!r}")

    target = {"home": fair_1x2["home"], "draw": fair_1x2["draw"], "away": fair_1x2["away"]}
    over_target = None
    if fair_totals and "over" in fair_totals:
        over_target = float(fair_totals["over"])
        # Raise on an unsupported line rather than quietly dropping the
        # constraint, which would leave the goal level unidentified.
        over_probability(score_matrix(1.4, 1.2), totals_line)

    # rho is fitted, not fixed. A plain Poisson systematically under-predicts
    # draws, and the shortfall grows with the goal total: pinning rho at a small
    # constant left a ~0.03 draw error on high-scoring lines, which is larger
    # than the edges we are trying to detect. Correcting draw frequency is
    # precisely what the Dixon-Coles rho term exists to do, so we let the sharp
    # prices choose it within its valid range.
    def loss(params):
        lam_h, lam_a = np.exp(params[:2])                # keeps both positive
        r = np.clip(params[2], -0.25, 0.25)
        mat = score_matrix(lam_h, lam_a, r)
        m = markets_from_matrix(mat)
        err = ((m["home"] - target["home"]) ** 2
               + (m["draw"] - target["draw"]) ** 2
               + (m["away"] - target["away"]) ** 2)
        if over_target is not None:
            # Weighted so the totals line pins overall goal level as firmly as
            # the 1X2 line pins the balance between the sides. Computed for the
            # ACTUAL posted line — Asian lines (2.75, 3.0) are common and an
            # earlier version silently skipped them, leaving the total free.
            err += 3.0 * (over_probability(mat, totals_line) - over_target) ** 2
        return err

    best, best_loss = None, np.inf
    for h0, a0 in ((1.5, 1.2), (1.2, 1.5), (2.0, 1.0), (1.0, 2.0), (1.35, 1.35)):
        for r0 in (rho, -0.12):
            res = minimize(loss, np.array([np.log(h0), np.log(a0), r0]),
                           method="Nelder-Mead",
                           options={"xatol": 1e-6, "fatol": 1e-12, "maxiter": 4000})
            if res.fun < best_loss:
                best, best_loss = res, res.fun

    lam_h, lam_a = np.exp(best.x[:2])
    rho = float(np.clip(best.x[2], -0.25, 0.25))
    fitted = markets_from_matrix(score_matrix(lam_h, lam_a, rho))
    errors = {k: fitted[k] - target[k] for k in target}
    if over_target is not None:
        errors[f"over_{totals_line}"] = (
            over_probability(score_matrix(lam_h, lam_a, rho), totals_line) - over_target)

    return float(lam_h), float(lam_a), {
        "max_error": float(max(abs(v) for v in errors.values())),
        "errors": errors,
        "fitted": fitted,
        "rho": rho,
        "converged": bool(best.success),
    }


def derive_markets(fair_1x2: dict, fair_totals: dict = None, totals_line: float = 2.5,
                   max_error: float = 0.02, rho: float = DEFAULT_RHO) -> dict:
    """
    Returns derived market probabilities, or {} if the fit is not good enough.

    Refusing to return anything on a poor fit is deliberate: a BTTS price derived
    from lambdas that do not reproduce the sharp 1X2 is not sharp-anchored at
    all, and would quietly become a model-priced bet inside a divergence arm.

    A totals line is REQUIRED. The 1X2 prices constrain the balance between the
    two sides but say almost nothing about the goal level, so with rho free the
    solver can reproduce them exactly at wildly different totals — and BTTS is
    driven mainly by the total. Without a totals anchor the derived BTTS is
    arbitrary, so we return nothing and simply do not bet that fixture.
    """
    if not fair_totals or "over" not in fair_totals:
        return {}

    lam_h, lam_a, diag = solve_lambdas(fair_1x2, fair_totals, totals_line, rho)
    if not diag["converged"] or diag["max_error"] > max_error:
        return {}
    out = dict(diag["fitted"])
    out["lambda_home"] = lam_h
    out["lambda_away"] = lam_a
    out["rho"] = diag["rho"]
    out["fit_max_error"] = diag["max_error"]
    return out
