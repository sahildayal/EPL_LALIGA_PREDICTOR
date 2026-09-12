"""Throwaway diagnostic: why does the model price some fixtures absurdly?

Prints, per fixture, whether each club is in the fitted index, its
(attack, defence), the effective weighted sample behind it, and the resulting
lambdas / market probabilities.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.data.canonical_teams import canonical
from src.models.dixon_coles import DixonColes

FIXTURES = {
    "epl": [("chelsea", "hull"), ("coventry", "brighton"), ("arsenal", "chelsea")],
    "laliga": [("malaga", "villarreal"), ("celta vigo", "malaga"),
               ("deportivo la coruna", "sevilla"), ("real madrid", "rayo vallecano")],
}


def main() -> int:
    df = pd.read_csv("data/processed/matches.csv", parse_dates=["date"])
    print(f"dataset: {len(df)} matches, latest {df.date.max().date()}")
    for league, pairs in FIXTURES.items():
        sub = df[df.league == league]
        ref = sub.date.max()
        model = DixonColes(halflife_days=365).fit(
            sub.home.tolist(), sub.away.tolist(),
            sub.home_goals.to_numpy(), sub.away_goals.to_numpy(),
            (ref - sub.date).dt.days.to_numpy())

        w = np.exp(-model.xi * (ref - sub.date).dt.days.to_numpy())
        eff = {}
        for team, weight in zip(sub.home.tolist(), w):
            eff[team] = eff.get(team, 0.0) + weight
        for team, weight in zip(sub.away.tolist(), w):
            eff[team] = eff.get(team, 0.0) + weight

        print(f"\n===== {league.upper()} | {len(sub)} matches | ref {ref.date()} "
              f"| home_adv {model.home_adv:.3f} | rho {model.rho:.3f} "
              f"| scale {getattr(model, 'scale', 1.0):.4f} =====")
        print(f"attack  pct20={np.percentile(model.attack,20):+.3f} "
              f"median={np.median(model.attack):+.3f} "
              f"pct80={np.percentile(model.attack,80):+.3f}")
        print(f"defence pct20={np.percentile(model.defence,20):+.3f} "
              f"median={np.median(model.defence):+.3f} "
              f"pct80={np.percentile(model.defence,80):+.3f}")

        for home, away in pairs:
            print(f"\n  --- {home} vs {away} ---")
            for t in (home, away):
                c = canonical(t, strict=False)
                if c in model.index:
                    i = model.index[c]
                    print(f"    {c:24s} IN INDEX  attack={model.attack[i]:+.3f} "
                          f"defence={model.defence[i]:+.3f}  eff_n={eff.get(c,0):.2f}")
                else:
                    print(f"    {c:24s} NOT FITTED (would use fallback prior)")
            try:
                lam, mu = model.lambdas(home, away)
                mk = model.market_probs(home, away)
                print(f"    lambdas: home={lam:.3f} away={mu:.3f} total={lam+mu:.3f}")
                print(f"    H/D/A {mk['home']:.3f}/{mk['draw']:.3f}/{mk['away']:.3f}  "
                      f"over2.5={mk['over_2.5']:.3f}  btts_yes={mk['btts_yes']:.3f}")
            except Exception as exc:                       # noqa: BLE001
                print(f"    lambdas failed: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
