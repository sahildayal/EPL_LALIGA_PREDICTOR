"""Calibration tests. Overconfidence is the failure mode that ruins Kelly staking."""
import numpy as np
import pandas as pd
import pytest

from src.models.calibration import (
    TemperatureScaling, IsotonicCalibrator, oof_calibrate,
)
from src.eval.metrics import expected_calibration_error, log_loss


def overconfident_sample(n=4000, seed=0, sharpen=2.2):
    """True probabilities plus a model that is systematically too sure of itself."""
    rng = np.random.default_rng(seed)
    base = rng.dirichlet([4.0, 3.0, 3.0], size=n)
    draws = rng.random(n)
    cum = base.cumsum(axis=1)
    y = (draws[:, None] > cum).sum(axis=1)
    sharp = base ** sharpen
    sharp /= sharp.sum(axis=1, keepdims=True)
    return sharp, y, base


# --- Temperature scaling ----------------------------------------------------

def test_temperature_reduces_ece_on_overconfident_model():
    probs, y, _ = overconfident_sample()
    before = expected_calibration_error(probs, y)
    after = expected_calibration_error(TemperatureScaling().fit_transform(probs, y), y)
    assert after < before
    assert after < 0.02


def test_temperature_above_one_for_overconfidence():
    probs, y, _ = overconfident_sample()
    assert TemperatureScaling().fit(probs, y).temperature > 1.0


def test_temperature_below_one_for_underconfidence():
    probs, y, base = overconfident_sample(sharpen=0.45)
    assert TemperatureScaling().fit(probs, y).temperature < 1.0


def test_temperature_improves_log_loss():
    probs, y, _ = overconfident_sample()
    cal = TemperatureScaling().fit_transform(probs, y)
    assert log_loss(cal, y) < log_loss(probs, y)


def test_temperature_preserves_ranking():
    """It may soften confidence but must never change which outcome is favoured."""
    probs, y, _ = overconfident_sample()
    cal = TemperatureScaling().fit_transform(probs, y)
    assert (cal.argmax(axis=1) == probs.argmax(axis=1)).all()


def test_temperature_output_is_a_valid_distribution():
    probs, y, _ = overconfident_sample()
    cal = TemperatureScaling().fit_transform(probs, y)
    assert np.allclose(cal.sum(axis=1), 1.0)
    assert (cal > 0).all()


def test_calibrated_model_stays_calibrated():
    """Calibrating an already-calibrated model should barely move it."""
    _, y, base = overconfident_sample()
    t = TemperatureScaling().fit(base, y).temperature
    assert 0.85 < t < 1.2


def test_transform_before_fit_raises():
    with pytest.raises(RuntimeError):
        TemperatureScaling().transform(np.array([[0.4, 0.3, 0.3]]))


# --- Isotonic ---------------------------------------------------------------

def test_isotonic_reduces_ece():
    probs, y, _ = overconfident_sample()
    before = expected_calibration_error(probs, y)
    after = expected_calibration_error(IsotonicCalibrator().fit_transform(probs, y), y)
    assert after < before


def test_isotonic_output_valid():
    probs, y, _ = overconfident_sample()
    cal = IsotonicCalibrator().fit_transform(probs, y)
    assert np.allclose(cal.sum(axis=1), 1.0)
    assert (cal >= 0).all()


def test_isotonic_transform_before_fit_raises():
    with pytest.raises(RuntimeError):
        IsotonicCalibrator().transform(np.array([[0.4, 0.3, 0.3]]))


# --- Out-of-fold wiring ------------------------------------------------------

def _frame(n=1200, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "date": pd.date_range("2015-01-01", periods=n, freq="D"),
        "result": rng.choice(["H", "D", "A"], size=n, p=[0.46, 0.25, 0.29]),
        "x": rng.normal(size=n),
    })


def test_oof_calibrate_returns_valid_probs():
    df = _frame()
    train, test = df.iloc[:1000], df.iloc[1000:]

    def model(tr, te):
        return np.tile([0.80, 0.10, 0.10], (len(te), 1))   # wildly overconfident

    out = oof_calibrate(model, train, test)
    assert out.shape == (len(test), 3)
    assert np.allclose(out.sum(axis=1), 1.0)


def test_oof_calibration_softens_an_overconfident_model():
    df = _frame(n=2000)
    train, test = df.iloc[:1600], df.iloc[1600:]

    def model(tr, te):
        return np.tile([0.80, 0.10, 0.10], (len(te), 1))

    raw = model(train, test)
    cal = oof_calibrate(model, train, test)
    y = test.result.map({"H": 0, "D": 1, "A": 2}).to_numpy()
    assert cal[:, 0].mean() < raw[:, 0].mean()          # pulled back toward reality
    assert log_loss(cal, y) < log_loss(raw, y)


def test_oof_calibrate_passes_through_when_model_returns_none():
    df = _frame()
    assert oof_calibrate(lambda tr, te: None, df.iloc[:1000], df.iloc[1000:]) is None
