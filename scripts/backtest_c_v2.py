"""
The go-live gate for arm C_v2: CatBoost on pi-ratings against arm C's model.

    python scripts/backtest_c_v2.py            # full run, ~1h on 8 cores
    python scripts/backtest_c_v2.py --quick    # last 3 seasons only

Agreed bar (2026-11-22): C_v2 goes live only if it beats C's OWN model on
walk-forward RPS and log loss over the same folds. It does not have to beat the
market; no model in this repo ever has.

Both sides are scored the way they are used live, which is NOT how
src/eval/backtest.py works. That harness freezes a model for a whole test
season, but arm C refits before every stake run, so a frozen comparison would
handicap whichever model benefits more from fresh results. Here each test
season is cut into calendar months and both models are re-trained on
everything before the month starts:

  C   Dixon-Coles, 365-day halflife, per league, shrunk to the promoted-club
      prior (matchweek._shrink_to_prior) exactly as collect_model_probs does.
      Trained on the last TRAIN_SEASONS seasons for speed: at a 365-day
      halflife anything older carries under 0.4% weight.
  v2  CatBoost multiclass on pi-ratings (Constantinou & Fenton 2013), computed
      strictly causally match by match. Two variants: ratings only (the
      literature's best goals-only model), and ratings plus the rolling form
      features already in matches.csv.

1X2 only: that is what both the literature and the harness score, and what a
live C_v2 would price (plus the NOT sides, which follow from it).
"""
import argparse
import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from src.eval.metrics import log_loss  # noqa: E402

CSV = "data/processed/matches.csv"
# One line per finished league-month, appended as each completes, so a crash
# (the first full run died at 280/324 on a broken pandas install) resumes
# instead of refitting from scratch.
ROWS = Path("notes/c_v2_backtest_rows.jsonl")
TEST_SEASONS = 16
TRAIN_SEASONS = 8
RESULT_IDX = {"H": 0, "D": 1, "A": 2}

# Pi-rating constants from Constantinou & Fenton (2013).
PI_LAMBDA, PI_GAMMA, PI_B, PI_C = 0.035, 0.7, 10.0, 3.0

FORM_COLS = ["h_ppg", "h_gd_pg", "h_form_ppg", "h_venue_gf_pg", "h_venue_ga_pg",
             "h_sot_pg", "h_sot_against_pg", "h_rest_days",
             "a_ppg", "a_gd_pg", "a_form_ppg", "a_venue_gf_pg", "a_venue_ga_pg",
             "a_sot_pg", "a_sot_against_pg", "a_rest_days"]


def rps(probs, outcomes) -> float:
    """Ranked probability score for ordered H/D/A outcomes. Lower is better."""
    p = np.asarray(probs, dtype=float)
    y = np.zeros_like(p)
    y[np.arange(len(outcomes)), outcomes] = 1.0
    cp, cy = np.cumsum(p, axis=1)[:, :2], np.cumsum(y, axis=1)[:, :2]
    return float(np.mean(np.sum((cp - cy) ** 2, axis=1) / 2.0))


def _expected_gd(r: float) -> float:
    return np.sign(r) * (PI_B ** (abs(r) / PI_C) - 1.0)


def add_pi_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-match pi-ratings for every row, updated only AFTER the match is played."""
    df = df.sort_values("date").copy()
    cols = {k: np.zeros(len(df)) for k in ("pi_hh", "pi_ha", "pi_ah", "pi_aa", "pi_gd")}
    ratings = {}                                   # (league, team) -> [home, away]
    for i, row in enumerate(df.itertuples(index=False)):
        h = ratings.setdefault((row.league, row.home), [0.0, 0.0])
        a = ratings.setdefault((row.league, row.away), [0.0, 0.0])
        pred = _expected_gd(h[0]) - _expected_gd(a[1])
        cols["pi_hh"][i], cols["pi_ha"][i] = h
        cols["pi_ah"][i], cols["pi_aa"][i] = a
        cols["pi_gd"][i] = pred
        err = (row.home_goals - row.away_goals) - pred
        psi = np.sign(err) * PI_C * np.log10(1.0 + abs(err))
        h[0] += psi * PI_LAMBDA
        h[1] += psi * PI_LAMBDA * PI_GAMMA
        a[1] -= psi * PI_LAMBDA
        a[0] -= psi * PI_LAMBDA * PI_GAMMA
    for k, v in cols.items():
        df[k] = v
    return df


def dc_probs(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Arm C's live recipe (collect_model_probs), for one league."""
    from src.models.dixon_coles import DixonColes
    from src.pipeline.matchweek import _shrink_to_prior

    ref = train.date.max()
    days = (ref - train.date).dt.days.to_numpy()
    m = DixonColes(halflife_days=365).fit(
        train.home.tolist(), train.away.tolist(),
        train.home_goals.to_numpy(), train.away_goals.to_numpy(), days)
    fallback = (float(np.percentile(m.attack, 20)), float(np.percentile(m.defence, 80)))
    _shrink_to_prior(m, train, days, fallback)
    out = []
    for h, a in zip(test.home, test.away):
        priors = {t: fallback for t in (h, a) if t not in m.index}
        mk = m.market_probs(h, a, priors=priors)
        out.append([mk["home"], mk["draw"], mk["away"]])
    return np.array(out)


def cb_probs(train: pd.DataFrame, test: pd.DataFrame, features: list) -> np.ndarray:
    from catboost import CatBoostClassifier
    model = CatBoostClassifier(iterations=500, depth=6, learning_rate=0.05,
                               loss_function="MultiClass", verbose=False,
                               random_seed=7, thread_count=1,
                               allow_writing_files=False)
    model.fit(train[features], train.result.map(RESULT_IDX), cat_features=["league"])
    p = model.predict_proba(test[features])
    return p[:, np.argsort(model.classes_)]


def _chunk(args):
    """One (league, test month): train on everything before it, score the month."""
    league, start, end, df = args
    # Scored rows: this league and month, with market odds, so every model is
    # compared on identical matches. Training uses every row before the month.
    test = df[(df.league == league) & (df.date >= start) & (df.date < end)]
    test = test.dropna(subset=["odds_h", "odds_d", "odds_a"])
    if test.empty:
        return []
    seasons = sorted(df[df.date < start].season.unique())[-TRAIN_SEASONS:]
    past = df[(df.date < start) & df.season.isin(seasons)]
    y = test.result.map(RESULT_IDX).to_numpy()
    pi = ["league", "pi_hh", "pi_ha", "pi_ah", "pi_aa", "pi_gd"]
    preds = {
        "C_dixon_coles": dc_probs(past[past.league == league], test),
        "v2_catboost_pi": cb_probs(past, test, pi),
        "v2_catboost_pi_form": cb_probs(past, test, pi + FORM_COLS),
    }
    odds = test[["odds_h", "odds_d", "odds_a"]].to_numpy(float)
    preds["MARKET"] = (1 / odds) / (1 / odds).sum(axis=1, keepdims=True)
    return [{"league": league, "season": test.season.iloc[0], "model": k,
             "y": y.tolist(), "p": np.asarray(v).tolist()} for k, v in preds.items()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="last 3 seasons only")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--report-only", action="store_true",
                    help="re-print the last run's saved predictions without refitting")
    args = ap.parse_args()

    df = pd.read_csv(CSV, parse_dates=["date"], dtype={"season": str})
    df = df.dropna(subset=["home_goals", "away_goals", "result"])
    df = add_pi_ratings(df)
    df[FORM_COLS] = df[FORM_COLS].fillna(df[FORM_COLS].median())
    current = sorted(df.season.unique())[-1]          # in progress: never scored

    jobs = []
    for league in sorted(df.league.unique()):
        lg = df[(df.league == league) & (df.season != current)].dropna(subset=["odds_h"])
        for s in sorted(lg.season.unique())[-(3 if args.quick else TEST_SEASONS):]:
            dates = lg[lg.season == s].date
            months = pd.date_range(dates.min().to_period("M").to_timestamp(),
                                   dates.max() + pd.offsets.MonthBegin(1), freq="MS")
            jobs += [(league, a, b, df) for a, b in zip(months[:-1], months[1:])]

    if args.report_only:
        report(_load_rows())
        return
    done = {(r["league"], r["month"]) for r in _load_rows()}
    todo = [j for j in jobs if (j[0], str(j[1])[:7]) not in done]
    print(f"{len(jobs)} league-months, {len(jobs) - len(todo)} already done, "
          f"{len(todo)} to fit...", flush=True)
    ROWS.parent.mkdir(exist_ok=True)
    failed = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_chunk, j): j for j in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            league, start = futures[fut][0], str(futures[fut][1])[:7]
            try:
                out = fut.result()
            except Exception as exc:                          # noqa: BLE001
                failed.append((league, start, f"{type(exc).__name__}: {exc}"))
                continue
            with ROWS.open("a", encoding="utf-8") as fh:
                for r in out:
                    fh.write(json.dumps(dict(r, month=start)) + "\n")
            if i % 20 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    if failed:
        # A gap would bias the comparison toward whichever months survived.
        print(f"\n{len(failed)} league-month(s) FAILED; re-run to retry them:")
        for f in failed:
            print("  ", *f)
        sys.exit(1)
    report(_load_rows())


def _load_rows() -> list:
    if not ROWS.exists():
        return []
    return [json.loads(line) for line in ROWS.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def report(rows):
    by = {}
    for r in rows:
        k = (r["league"], r["season"], r["model"])
        by.setdefault(k, ([], []))
        by[k][0].extend(r["y"])
        by[k][1].extend(r["p"])
    folds = sorted({(lg, s) for lg, s, _ in by})
    models = sorted({m for *_, m in by})
    table = []
    for lg, s in folds:
        for m in models:
            if (lg, s, m) in by:
                y, p = by[(lg, s, m)]
                table.append({"league": lg, "season": s, "model": m, "n": len(y),
                              "rps": rps(np.array(p), np.array(y)),
                              "log_loss": log_loss(np.array(p), np.array(y))})
    t = pd.DataFrame(table)
    base = t[t.model == "C_dixon_coles"].set_index(["league", "season"])
    print("\n== mean over folds (lower is better) ==")
    summary = t.groupby("model")[["rps", "log_loss"]].mean().sort_values("rps")
    for m in models:
        mine = t[t.model == m].set_index(["league", "season"])
        common = mine.index.intersection(base.index)
        summary.loc[m, "beats_C_rps_folds"] = int(
            (mine.loc[common, "rps"] < base.loc[common, "rps"]).sum())
        summary.loc[m, "beats_C_ll_folds"] = int(
            (mine.loc[common, "log_loss"] < base.loc[common, "log_loss"]).sum())
        summary.loc[m, "folds"] = len(common)
    print(f"{'model':<22}{'rps':>9}{'log_loss':>10}{'beats C (rps)':>15}"
          f"{'beats C (ll)':>14}{'folds':>7}")
    for m, r in summary.iterrows():
        print(f"{m:<22}{r.rps:>9.5f}{r.log_loss:>10.5f}{int(r.beats_C_rps_folds):>15}"
              f"{int(r.beats_C_ll_folds):>14}{int(r.folds):>7}")
    out = Path("notes/c_v2_backtest.csv")
    out.parent.mkdir(exist_ok=True)
    t.to_csv(out, index=False)
    print(f"\nper-fold results: {out}")


if __name__ == "__main__":
    main()
