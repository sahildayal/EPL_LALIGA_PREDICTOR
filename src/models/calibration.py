"""
Probability calibration.

Kelly staking is superlinearly sensitive to overstated p, so an overconfident
model is a bankroll hazard regardless of how well it ranks matches. The baseline
board made this concrete: adding time decay to XGBoost pushed its ECE from
0.0501 to 0.0721 while its log loss also worsened — it became confidently wrong.
The market, by contrast, sits at 0.0247-0.0289.

Two calibrators, deliberately ordered simplest-first, because the same board
showed complexity hurting at every step:

  TemperatureScaling  one parameter, cannot reshape the ranking, hard to overfit
  IsotonicCalibrator  flexible, per-class, needs far more data to be safe

Both must be fitted OUT OF FOLD. Calibrating on the same data a model was
trained on measures nothing and produces a confident-looking lie.
"""
import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression

EPS = 1e-12


def _norm(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, None)
    return p / p.sum(axis=1, keepdims=True)


class TemperatureScaling:
    """
    Divides the logits by a scalar T fitted to minimise log loss.

    T > 1 softens an overconfident model; T < 1 sharpens an underconfident one.
    It cannot change which outcome is favoured, only how strongly — which is
    exactly the conservative behaviour we want.
    """

    def __init__(self):
        self.temperature = 1.0
        self.is_fitted = False

    def fit(self, probs, outcomes):
        p = _norm(probs)
        y = np.asarray(outcomes, dtype=int)
        logits = np.log(p)

        def nll(log_t):
            t = np.exp(log_t)                      # keeps T strictly positive
            scaled = logits / t
            scaled -= scaled.max(axis=1, keepdims=True)
            e = np.exp(scaled)
            q = e / e.sum(axis=1, keepdims=True)
            return -np.mean(np.log(np.clip(q[np.arange(len(y)), y], EPS, None)))

        res = minimize_scalar(nll, bounds=(np.log(0.2), np.log(8.0)), method="bounded")
        self.temperature = float(np.exp(res.x))
        self.is_fitted = True
        return self

    def transform(self, probs):
        if not self.is_fitted:
            raise RuntimeError("TemperatureScaling is not fitted")
        logits = np.log(_norm(probs)) / self.temperature
        logits -= logits.max(axis=1, keepdims=True)
        e = np.exp(logits)
        return e / e.sum(axis=1, keepdims=True)

    def fit_transform(self, probs, outcomes):
        return self.fit(probs, outcomes).transform(probs)


class IsotonicCalibrator:
    """
    One-vs-rest isotonic regression per outcome, renormalised.

    More flexible than temperature scaling and can fix non-monotone miscalibration,
    but it has far more effective parameters and will happily memorise a small
    calibration set. Prefer temperature scaling unless the harness shows this
    winning on held-out folds.
    """

    def __init__(self, n_classes: int = 3):
        self.n_classes = n_classes
        self.models = []
        self.is_fitted = False

    def fit(self, probs, outcomes):
        p = _norm(probs)
        y = np.asarray(outcomes, dtype=int)
        self.models = []
        for k in range(self.n_classes):
            iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            iso.fit(p[:, k], (y == k).astype(float))
            self.models.append(iso)
        self.is_fitted = True
        return self

    def transform(self, probs):
        if not self.is_fitted:
            raise RuntimeError("IsotonicCalibrator is not fitted")
        p = _norm(probs)
        out = np.column_stack([m.predict(p[:, k]) for k, m in enumerate(self.models)])
        out = np.clip(out, EPS, None)
        return out / out.sum(axis=1, keepdims=True)

    def fit_transform(self, probs, outcomes):
        return self.fit(probs, outcomes).transform(probs)


def oof_calibrate(model_fn, train, test, outcome_col="result", n_splits: int = 4,
                  calibrator="temperature"):
    """
    Fits a calibrator on out-of-fold predictions, then applies it to the test set.

    The training window is split chronologically: each inner slice is predicted by
    a model fitted only on earlier slices, so the calibration data is genuinely
    unseen. Calibrating on in-sample predictions would fit a model to its own
    overconfidence and report that it had cured it.
    """
    mapping = {"H": 0, "D": 1, "A": 2}
    cuts = np.array_split(np.arange(len(train)), n_splits + 1)

    oof_probs, oof_y = [], []
    for i in range(1, len(cuts)):
        inner_train = train.iloc[np.concatenate(cuts[:i])]
        inner_val = train.iloc[cuts[i]]
        if len(inner_train) < 200 or len(inner_val) == 0:
            continue
        p = model_fn(inner_train, inner_val)
        if p is None:
            continue
        oof_probs.append(np.asarray(p, dtype=float))
        oof_y.append(inner_val[outcome_col].map(mapping).to_numpy())

    test_probs = model_fn(train, test)
    if test_probs is None:
        return None
    if not oof_probs:
        return np.asarray(test_probs, dtype=float)

    cal = TemperatureScaling() if calibrator == "temperature" else IsotonicCalibrator()
    cal.fit(np.vstack(oof_probs), np.concatenate(oof_y))
    return cal.transform(np.asarray(test_probs, dtype=float))
