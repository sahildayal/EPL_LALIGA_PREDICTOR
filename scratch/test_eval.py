"""Metric and harness tests. These gate every model claim we make."""
import numpy as np
import pandas as pd
import pytest

from src.eval.metrics import (
    log_loss, brier_score, accuracy, expected_calibration_error,
    calibration_curve, closing_line_value, roi_with_bands, summarise,
)
from src.eval.backtest import season_folds, run_backtest, leaderboard, market_probs


# --- Metrics ---------------------------------------------------------------

def test_perfect_forecast_scores_zero():
    p = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert log_loss(p, ["H", "D", "A"]) < 1e-10
    assert brier_score(p, ["H", "D", "A"]) < 1e-10
    assert accuracy(p, ["H", "D", "A"]) == 1.0


def test_uniform_forecast_equals_log_three():
    p = [[1 / 3] * 3] * 20
    assert log_loss(p, ["H"] * 20) == pytest.approx(np.log(3), abs=1e-9)


def test_confidently_wrong_is_heavily_penalised():
    confident = log_loss([[0.98, 0.01, 0.01]], ["A"])
    hedged = log_loss([[0.4, 0.3, 0.3]], ["A"])
    assert confident > hedged * 3


def test_string_and_index_outcomes_agree():
    p = [[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]]
    assert log_loss(p, ["H", "A"]) == pytest.approx(log_loss(p, [0, 2]))


def test_probs_are_renormalised_not_trusted():
    assert log_loss([[2.0, 1.0, 1.0]], ["H"]) == pytest.approx(log_loss([[0.5, 0.25, 0.25]], ["H"]))


def test_bad_shapes_and_labels_raise():
    with pytest.raises(ValueError):
        log_loss([[0.5, 0.5]], ["H"])
    with pytest.raises(ValueError):
        log_loss([[0.4, 0.3, 0.3]], ["X"])
    with pytest.raises(ValueError):
        log_loss([[0.4, 0.3, 0.3]], ["H", "D"])


# --- Calibration -----------------------------------------------------------

def test_calibrated_forecast_has_low_ece():
    rng = np.random.default_rng(0)
    n = 4000
    p_home = rng.uniform(0.15, 0.75, n)
    rest = 1 - p_home
    probs = np.column_stack([p_home, rest * 0.45, rest * 0.55])
    draws = rng.random(n)
    y = np.where(draws < probs[:, 0], 0,
         np.where(draws < probs[:, 0] + probs[:, 1], 1, 2))
    assert expected_calibration_error(probs, y) < 0.03


def test_overconfident_forecast_has_high_ece():
    """The failure mode that ruins Kelly staking must be visible in the metric."""
    rng = np.random.default_rng(1)
    n = 3000
    true_p = np.full(n, 0.45)
    over = np.column_stack([np.full(n, 0.85), np.full(n, 0.08), np.full(n, 0.07)])
    y = (rng.random(n) >= true_p).astype(int) * 2       # H or A
    assert expected_calibration_error(over, y) > 0.2


def test_calibration_curve_bins_cover_everything():
    probs = np.tile([0.5, 0.3, 0.2], (100, 1))
    curve = calibration_curve(probs, ["H"] * 100, bins=10)
    assert len(curve) == 10
    assert sum(b["n"] for b in curve) == 300           # 100 matches x 3 outcomes


# --- Betting metrics --------------------------------------------------------

def test_clv_positive_when_price_beats_close():
    clv = closing_line_value([0.50, 0.40], [0.55, 0.44])
    assert clv["mean_clv_pct"] == pytest.approx(10.0)
    assert clv["beat_close_rate"] == 1.0


def test_clv_negative_when_line_moves_against_us():
    assert closing_line_value([0.50], [0.45])["mean_clv_pct"] == pytest.approx(-10.0)


def test_clv_ignores_missing_closing_prices():
    assert closing_line_value([0.5, 0.5], [0.55, np.nan])["n"] == 1


def test_roi_bands_span_zero_on_noise():
    """A break-even sample must not be reported as a real edge."""
    rng = np.random.default_rng(3)
    stakes = np.full(150, 100.0)
    pnls = rng.choice([-100.0, 100.0], size=150)
    r = roi_with_bands(stakes, pnls)
    assert r["ci_low"] < 0 < r["ci_high"]


def test_roi_computed_correctly():
    r = roi_with_bands([100, 100], [50, -20])
    assert r["roi_pct"] == pytest.approx(15.0)


def test_roi_handles_empty():
    assert roi_with_bands([], [])["roi_pct"] is None


# --- Harness ----------------------------------------------------------------

def _synthetic(n_seasons=12, per_season=40, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_seasons):
        for i in range(per_season):
            r = rng.choice(["H", "D", "A"], p=[0.46, 0.25, 0.29])
            rows.append({
                "date": pd.Timestamp("2010-01-01") + pd.Timedelta(days=s * 365 + i),
                "season": f"s{s:02d}", "league": "epl", "result": r,
                "odds_h": 2.1, "odds_d": 3.4, "odds_a": 3.6,
                "feat": rng.normal(),
            })
    return pd.DataFrame(rows)


def test_folds_never_leak_future_data():
    df = _synthetic()
    for f in season_folds(df, min_train_seasons=8):
        assert f.train.date.max() < f.test.date.min()
        assert set(f.test.season).isdisjoint(set(f.train.season))


def test_fold_count_matches_seasons():
    df = _synthetic(n_seasons=12)
    assert len(season_folds(df, min_train_seasons=8)) == 4


def test_market_probs_sum_to_one():
    p = market_probs(_synthetic())
    assert np.allclose(p.sum(axis=1), 1.0)


def test_backtest_always_includes_market_baseline():
    res = run_backtest(_synthetic(), models={}, verbose=False)
    assert set(res.model) == {"MARKET", "base_rate"}


def test_backtest_scores_a_custom_model():
    def flat(train, test):
        return np.tile([0.46, 0.25, 0.29], (len(test), 1))
    res = run_backtest(_synthetic(), models={"flat": flat}, verbose=False)
    assert "flat" in set(res.model)
    lb = leaderboard(res)
    assert "vs_market" in lb.columns
    assert lb.loc[lb.model == "MARKET", "vs_market"].iloc[0] == 0.0


def test_failing_model_does_not_abort_the_run():
    def broken(train, test):
        raise RuntimeError("boom")
    res = run_backtest(_synthetic(), models={"broken": broken}, verbose=False)
    assert "broken" not in set(res.model)
    assert "MARKET" in set(res.model)


def test_wrong_shape_from_model_raises():
    def bad(train, test):
        return np.tile([0.5, 0.5], (len(test), 1))
    with pytest.raises(ValueError):
        run_backtest(_synthetic(), models={"bad": bad}, verbose=False)


def test_summarise_shape():
    s = summarise([[0.5, 0.3, 0.2]], ["H"])
    assert set(s) == {"n", "log_loss", "brier", "accuracy", "ece"}
