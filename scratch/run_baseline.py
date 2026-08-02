"""
Produces the documented baseline board for Phase 2.

Every Phase 3 model change is measured against this. Numbers here are produced
by walk-forward CV on real matches, not asserted.
"""
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

from src.eval.backtest import run_backtest, print_leaderboard, leaderboard

CSV = "data/processed/matches.csv"
DECAY_HALFLIFE_DAYS = 730.0


def _feature_columns(df):
    cols = [c for c in df.columns
            if c.startswith(("h_", "a_")) or c.endswith(("_diff", "_played"))]
    return [c for c in dict.fromkeys(cols) if df[c].notna().mean() > 0.9]


def _weights(train):
    age = (train.date.max() - train.date).dt.days
    return np.exp(-np.log(2) * age / DECAY_HALFLIFE_DAYS).to_numpy()


def make_xgb(use_decay=True):
    def fn(train, test):
        feats = _feature_columns(train)
        sc = StandardScaler().fit(train[feats])
        m = xgb.XGBClassifier(
            objective="multi:softprob", num_class=3, eval_metric="mlogloss",
            max_depth=4, learning_rate=0.05, n_estimators=400, subsample=0.8,
            colsample_bytree=0.8, reg_lambda=2.0, random_state=42, n_jobs=-1,
        )
        y = train.result.map({"H": 0, "D": 1, "A": 2})
        m.fit(sc.transform(train[feats]), y,
              sample_weight=_weights(train) if use_decay else None)
        return m.predict_proba(sc.transform(test[feats]))
    return fn


def logistic(train, test):
    feats = _feature_columns(train)
    sc = StandardScaler().fit(train[feats])
    m = LogisticRegression(max_iter=3000, C=0.5)
    m.fit(sc.transform(train[feats]), train.result.map({"H": 0, "D": 1, "A": 2}))
    return m.predict_proba(sc.transform(test[feats]))


def elo_style(train, test):
    """
    Cheap strength baseline: season-to-date points-per-game difference mapped
    through a fitted multinomial logit. Sanity check that richer models earn
    their complexity.
    """
    cols = ["ppg_diff", "gd_pg_diff", "form_ppg_diff"]
    sc = StandardScaler().fit(train[cols])
    m = LogisticRegression(max_iter=2000)
    m.fit(sc.transform(train[cols]), train.result.map({"H": 0, "D": 1, "A": 2}))
    return m.predict_proba(sc.transform(test[cols]))


_XGB_CACHE = {}


def _cached_xgb(train, test):
    """
    Memoises the XGB prediction per fold.

    Each market-blend weight previously refit the same model from scratch, so a
    run did four XGB fits per fold instead of two. The fold is keyed by its train
    /test boundary, which is unique within a run.
    """
    key = (train.index[0], train.index[-1], test.index[0], test.index[-1], len(train), len(test))
    if key not in _XGB_CACHE:
        _XGB_CACHE[key] = make_xgb(use_decay=True)(train, test)
    return _XGB_CACHE[key]


def market_shrunk(weight):
    """Market blended toward the model, to test whether the model adds anything."""
    def fn(train, test):
        odds = test[["odds_h", "odds_d", "odds_a"]].to_numpy(float)
        inv = 1.0 / odds
        mkt = inv / inv.sum(axis=1, keepdims=True)
        return (1 - weight) * mkt + weight * _cached_xgb(train, test)
    return fn


def main():
    df = pd.read_csv(CSV, parse_dates=["date"])
    print(f"dataset: {len(df):,} matches | {df.date.min().date()} -> {df.date.max().date()}")

    models = {
        "xgb_pit": make_xgb(use_decay=False),
        "xgb_pit_decay": make_xgb(use_decay=True),
        "logistic_pit": logistic,
        "strength_only": elo_style,
        "market+10%model": market_shrunk(0.10),
        "market+25%model": market_shrunk(0.25),
    }

    for league in ["epl", "laliga"]:
        sub = df[df.league == league]
        print(f"\n{'=' * 78}\n{league.upper()}  ({len(sub):,} matches)\n{'=' * 78}")
        res = run_backtest(sub, models, min_train_seasons=8, verbose=True)
        print_leaderboard(res)
        res.to_csv(f"data/processed/baseline_{league}.csv", index=False)
        leaderboard(res).to_csv(f"data/processed/baseline_board_{league}.csv", index=False)


if __name__ == "__main__":
    main()
