"""
Phase 3 task 14: does blending help, and does calibration help?

Blend weights are fitted WALK-FORWARD: the weight used on fold k is chosen on
folds < k only. Sweeping weights on the test folds and reporting the best would
be the same maximum-selection bias that makes the old parlay engine report
+19.4% edges — the number would look good and mean nothing.
"""
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from src.eval.backtest import season_folds, market_probs, outcomes
from src.eval.metrics import log_loss, expected_calibration_error
from src.models.dixon_coles import DixonColes
from src.models.calibration import TemperatureScaling

CSV = "data/processed/matches.csv"
GRID = np.round(np.arange(0.0, 1.01, 0.05), 2)


def _promoted_prior(m, pct=20):
    return float(np.percentile(m.attack, pct)), float(np.percentile(m.defence, 100 - pct))


def fit_dc(train, test, count, halflife):
    ref = train.date.max()
    if count == "goals":
        sub = train
        hc, ac, scale = sub.home_goals.to_numpy(), sub.away_goals.to_numpy(), 1.0
    else:
        sub = train.dropna(subset=["home_sot", "away_sot"])
        if len(sub) < 500:
            return None
        hc, ac = sub.home_sot.to_numpy(), sub.away_sot.to_numpy()
        scale = float((sub.home_goals.sum() + sub.away_goals.sum()) /
                      max(sub.home_sot.sum() + sub.away_sot.sum(), 1.0))
    days = (ref - sub.date).dt.days.to_numpy()
    m = DixonColes(halflife_days=halflife).fit(
        sub.home.tolist(), sub.away.tolist(), hc, ac, days, scale=scale)
    fb = _promoted_prior(m)
    priors = {t: fb for t in set(test.home) | set(test.away) if t not in m.index}
    return m.predict_proba(list(zip(test.home, test.away)), priors=priors)


def best_weight(history):
    """Weight minimising pooled log loss over all previous folds."""
    if not history:
        return 0.0
    p_a = np.vstack([h["a"] for h in history])
    p_b = np.vstack([h["b"] for h in history])
    y = np.concatenate([h["y"] for h in history])
    losses = [log_loss((1 - w) * p_a + w * p_b, y) for w in GRID]
    return float(GRID[int(np.argmin(losses))])


def run(df, league):
    folds = season_folds(df.dropna(subset=["odds_h", "odds_d", "odds_a"]), 8)
    hist_shots, hist_mkt = [], []
    rows = []

    for f in folds:
        y = outcomes(f.test)
        mkt = market_probs(f.test)
        dc_g = fit_dc(f.train, f.test, "goals", 365)
        dc_s = fit_dc(f.train, f.test, "shots", 365)
        if dc_g is None or dc_s is None:
            continue

        # Calibrate DC using an inner chronological holdout of the training window.
        cut = int(len(f.train) * 0.8)
        inner_tr, inner_val = f.train.iloc[:cut], f.train.iloc[cut:]
        cal_g = dc_g
        try:
            p_val = fit_dc(inner_tr, inner_val, "goals", 365)
            if p_val is not None:
                ts = TemperatureScaling().fit(p_val, outcomes(inner_val))
                cal_g = ts.transform(dc_g)
        except Exception:
            pass

        w_shots = best_weight(hist_shots)
        blend_gs = (1 - w_shots) * dc_g + w_shots * dc_s

        w_mkt = best_weight(hist_mkt)
        blend_mkt = (1 - w_mkt) * mkt + w_mkt * dc_g

        for name, p in [("MARKET", mkt), ("dc_goals", dc_g), ("dc_shots", dc_s),
                        ("dc_goals_calibrated", cal_g),
                        (f"dc_goals+shots(wf)", blend_gs),
                        (f"market+dc(wf)", blend_mkt)]:
            rows.append({"fold": f.name, "model": name, "n": len(y),
                         "log_loss": log_loss(p, y),
                         "ece": expected_calibration_error(p, y)})

        rows.append({"fold": f.name, "model": "_w_shots", "n": len(y),
                     "log_loss": w_shots, "ece": np.nan})
        rows.append({"fold": f.name, "model": "_w_market_dc", "n": len(y),
                     "log_loss": w_mkt, "ece": np.nan})

        hist_shots.append({"a": dc_g, "b": dc_s, "y": y})
        hist_mkt.append({"a": mkt, "b": dc_g, "y": y})

    res = pd.DataFrame(rows)
    weights = res[res.model.str.startswith("_")]
    scores = res[~res.model.str.startswith("_")]

    agg = scores.groupby("model").agg(folds=("fold", "nunique"),
                                      log_loss=("log_loss", "mean"),
                                      ece=("ece", "mean")).reset_index()
    mkt_ll = agg.loc[agg.model == "MARKET", "log_loss"].iloc[0]
    agg["vs_market"] = (agg.log_loss - mkt_ll).round(4)
    agg = agg.sort_values("log_loss")

    print(f"\n{'=' * 70}\n{league.upper()}\n{'=' * 70}")
    w = max(len(m) for m in agg.model)
    print(f"  {'model':<{w}}  {'logloss':>8}  {'vs mkt':>8}  {'ece':>7}")
    print("  " + "-" * (w + 30))
    for r in agg.itertuples(index=False):
        print(f"  {r.model:<{w}}  {r.log_loss:8.4f}  {r.vs_market:+8.4f}  {r.ece:7.4f}")

    for key, label in [("_w_shots", "shots weight in dc blend"),
                       ("_w_market_dc", "dc weight in market blend")]:
        vals = weights[weights.model == key].log_loss.to_numpy()
        if len(vals):
            print(f"\n  {label}: mean {vals.mean():.3f}, final {vals[-1]:.2f}, "
                  f"range {vals.min():.2f}-{vals.max():.2f}")
    return res


def main():
    df = pd.read_csv(CSV, parse_dates=["date"])
    for league in ["epl", "laliga"]:
        out = run(df[df.league == league], league)
        out.to_csv(f"data/processed/blend_{league}.csv", index=False)


if __name__ == "__main__":
    main()
