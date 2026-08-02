"""Adds Dixon-Coles (goals and shots variants) to the baseline board."""
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from src.eval.backtest import run_backtest, print_leaderboard, leaderboard
from src.models.dixon_coles import DixonColes

CSV = "data/processed/matches.csv"


def _promoted_prior(model, pct=20):
    """
    Prior for a club with no top-flight history in the training window.

    Backtesting cannot call ClubElo as of a past date, so we use the empirical
    fact that promoted sides perform near the bottom of the division: the 20th
    percentile of fitted attack and defence. Live, elo_priors() supplies a real
    ClubElo rating instead, which is strictly better information.
    """
    a = float(np.percentile(model.attack, pct))
    d = float(np.percentile(model.defence, 100 - pct))
    return a, d


def make_dc(halflife, count="goals"):
    def fn(train, test):
        ref = train.date.max()
        days = (ref - train.date).dt.days.to_numpy()

        if count == "goals":
            hc, ac, scale = train.home_goals.to_numpy(), train.away_goals.to_numpy(), 1.0
        else:
            sub = train.dropna(subset=["home_sot", "away_sot"])
            if len(sub) < 500:
                return None
            days = (ref - sub.date).dt.days.to_numpy()
            hc, ac = sub.home_sot.to_numpy(), sub.away_sot.to_numpy()
            # Convert SoT expectation back to goals via the realised conversion rate.
            scale = float((sub.home_goals.sum() + sub.away_goals.sum()) /
                          max(sub.home_sot.sum() + sub.away_sot.sum(), 1.0))
            train = sub

        m = DixonColes(halflife_days=halflife).fit(
            train.home.tolist(), train.away.tolist(), hc, ac, days, scale=scale)

        fallback = _promoted_prior(m)
        priors = {t: fallback for t in set(test.home) | set(test.away) if t not in m.index}
        return m.predict_proba(list(zip(test.home, test.away)), priors=priors)
    return fn


def main():
    df = pd.read_csv(CSV, parse_dates=["date"])
    models = {
        "dc_goals_hl365": make_dc(365, "goals"),
        "dc_goals_hl730": make_dc(730, "goals"),
        "dc_goals_hl1460": make_dc(1460, "goals"),
        "dc_shots_hl365": make_dc(365, "shots"),
        "dc_shots_hl730": make_dc(730, "shots"),
    }
    for league in ["epl", "laliga"]:
        sub = df[df.league == league]
        print(f"\n{'=' * 78}\n{league.upper()}  ({len(sub):,} matches)\n{'=' * 78}")
        res = run_backtest(sub, models, min_train_seasons=8, verbose=False)
        print_leaderboard(res)
        res.to_csv(f"data/processed/baseline_dc_{league}.csv", index=False)


if __name__ == "__main__":
    main()
