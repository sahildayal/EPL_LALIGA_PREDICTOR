"""
Walk-forward backtesting.

Every model is scored the way it will actually be used: trained only on matches
that had already happened, then asked about the next season. A single random
split would leak future information through the season structure and flatter
every model — which is how projects convince themselves they beat a market they
have never actually beaten.

The market is included as a baseline in every run and is not optional. It is the
bar; a model that does not clear it has no business sizing a bet on its own.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.eval.metrics import summarise, log_loss

RESULT_TO_IDX = {"H": 0, "D": 1, "A": 2}


@dataclass
class Fold:
    name: str
    train: pd.DataFrame
    test: pd.DataFrame

    def __repr__(self):
        return (f"Fold({self.name}: train {len(self.train)} to "
                f"{self.train.date.max().date()}, test {len(self.test)})")


def season_folds(df: pd.DataFrame, min_train_seasons: int = 8) -> list:
    """
    Expanding-window folds, one per season.

    Fold k trains on every season before k and tests on season k, so training
    data always strictly precedes test data.
    """
    if "season" not in df.columns:
        raise ValueError("dataframe needs a 'season' column")
    df = df.sort_values("date")
    seasons = sorted(df.season.unique())
    folds = []
    for i in range(min_train_seasons, len(seasons)):
        test_season = seasons[i]
        train = df[df.season.isin(seasons[:i])]
        test = df[df.season == test_season]
        if len(train) and len(test):
            folds.append(Fold(test_season, train, test))
    return folds


def market_probs(df: pd.DataFrame) -> np.ndarray:
    """De-vigged market probabilities in H/D/A order, NaN where odds are absent."""
    cols = ["odds_h", "odds_d", "odds_a"]
    odds = df[cols].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / odds
    total = inv.sum(axis=1, keepdims=True)
    return inv / total


def outcomes(df: pd.DataFrame) -> np.ndarray:
    return df.result.map(RESULT_TO_IDX).to_numpy()


def run_backtest(df: pd.DataFrame, models: dict, min_train_seasons: int = 8,
                 require_odds: bool = True, verbose: bool = True) -> pd.DataFrame:
    """
    Scores each model across walk-forward folds.

    `models` maps a name to a callable(train_df, test_df) -> (n_test, 3) array of
    H/D/A probabilities. Returning None skips that model for that fold.

    With require_odds=True, scoring is restricted to matches that have market
    odds, so every model is compared against the market on identical rows.
    """
    if require_odds:
        df = df.dropna(subset=["odds_h", "odds_d", "odds_a"])

    folds = season_folds(df, min_train_seasons)
    if not folds:
        raise ValueError("no folds produced; check min_train_seasons against available seasons")

    rows = []
    for fold in folds:
        y = outcomes(fold.test)

        mkt = market_probs(fold.test)
        rows.append({"fold": fold.name, "model": "MARKET", **summarise(mkt, y)})

        prior = np.tile(np.bincount(outcomes(fold.train), minlength=3) / len(fold.train),
                        (len(fold.test), 1))
        rows.append({"fold": fold.name, "model": "base_rate", **summarise(prior, y)})

        for name, fn in models.items():
            try:
                p = fn(fold.train, fold.test)
            except Exception as exc:
                if verbose:
                    print(f"  [{fold.name}] {name} FAILED: {type(exc).__name__}: {exc}")
                continue
            if p is None:
                continue
            p = np.asarray(p, dtype=float)
            if p.shape != (len(fold.test), 3):
                raise ValueError(f"{name} returned {p.shape}, expected {(len(fold.test), 3)}")
            rows.append({"fold": fold.name, "model": name, **summarise(p, y)})

        if verbose:
            best = min((r for r in rows if r["fold"] == fold.name), key=lambda r: r["log_loss"])
            print(f"  {fold.name}: {len(fold.test):4d} matches | best = {best['model']} "
                  f"({best['log_loss']:.4f})")

    return pd.DataFrame(rows)


def leaderboard(results: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates folds into a ranked table, with each model's gap to the market.

    `beat_market_folds` is the honest headline: a model that wins on average but
    only in a minority of seasons is probably fitting one lucky season.
    """
    mkt = results[results.model == "MARKET"].set_index("fold")["log_loss"]
    agg = (results.groupby("model")
           .agg(folds=("fold", "nunique"), n=("n", "sum"),
                log_loss=("log_loss", "mean"), brier=("brier", "mean"),
                accuracy=("accuracy", "mean"), ece=("ece", "mean"))
           .reset_index())

    beat = {}
    for model, grp in results.groupby("model"):
        joined = grp.set_index("fold")["log_loss"]
        common = joined.index.intersection(mkt.index)
        beat[model] = int((joined.loc[common] < mkt.loc[common]).sum())
    agg["beat_market_folds"] = agg.model.map(beat)

    market_ll = agg.loc[agg.model == "MARKET", "log_loss"].iloc[0]
    agg["vs_market"] = (agg.log_loss - market_ll).round(4)
    return agg.sort_values("log_loss").reset_index(drop=True)


def print_leaderboard(results: pd.DataFrame):
    lb = leaderboard(results)
    width = max(len(m) for m in lb.model)
    print()
    print(f"  {'model':<{width}}  {'logloss':>8}  {'vs mkt':>8}  {'brier':>7}  "
          f"{'ece':>6}  {'acc':>6}  {'beat mkt':>9}")
    print("  " + "-" * (width + 54))
    for r in lb.itertuples(index=False):
        marker = "  <-- market" if r.model == "MARKET" else ""
        print(f"  {r.model:<{width}}  {r.log_loss:8.4f}  {r.vs_market:+8.4f}  "
              f"{r.brier:7.4f}  {r.ece:6.4f}  {r.accuracy:6.3f}  "
              f"{r.beat_market_folds:4d}/{r.folds:<4d}{marker}")
    print()
