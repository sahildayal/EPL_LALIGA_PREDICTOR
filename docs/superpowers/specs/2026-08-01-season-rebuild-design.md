# 2026/27 Season Rebuild — Design Spec

Status: **approved**, 2026-08-01. Supersedes the model layer of
`2026-08-01-epl-laliga-ucl-migration-design.md`.

## Why

A review on 2026-08-01 found the predictive core non-functional for club football.
Verified by execution, not inspection:

- `predictor.load_elo()` returns before the `CLUB_ELO` fallback, so every club
  resolves to the default 1700. Man City–Burnley and Real Madrid–Barcelona
  produced byte-identical Elo output. Elo is ~24% of the blend.
- `paper_trading._find_completed_event_id` queries only `fifa.world`,
  `uefa.nations`, `uefa.euro`. No EPL or La Liga bet can ever resolve.
- `master_dataset.csv` contains zero La Liga matches.
- 12 of 31 features are 99.8% NaN in training, median-imputed to a constant,
  but vary at inference — pure noise injection.
- `get_match_features` fabricates season-to-date tables (`htgs = avg_goals * 10`)
  that do not match how the training columns were built. Train/serve skew.
- No evaluation code existed anywhere in the repo: zero hits for `log_loss`,
  `brier`, `train_test_split`, `calibration`, `backtest`.

### The benchmark that set the strategy

> **Superseded — see "Walk-forward baseline board" below.** The single-split
> figures in this section were what motivated the strategy, but they flatter the
> models. Walk-forward CV over 16 seasons puts XGBoost at 1.0231 rather than
> 0.9564. The strategic conclusion held; the numbers did not. Kept for the record.

1,250 real EPL matches (Aug 2022 – Nov 2025), trained on 7,600 (2002–2022):

| Model | logloss (with odds) | logloss (no odds) |
|---|---|---|
| **Market (Bet365, de-vigged)** | **0.9512** | — |
| XGBoost | 0.9564 | 1.0028 |
| 6-model average | 0.9596 | **1.0000** |
| NeuralNetwork | 0.9602 | 1.0155 |
| GDA (LDA) | 0.9631 | 1.0310 |
| RandomForest | 0.9898 | 1.0400 |
| LogisticRegression | 0.9894 | 1.0508 |
| SVM | 0.9979 | 1.0199 |
| Base rate | 1.0603 | — |

Two conclusions:

1. **Nothing beats the market.** Best configuration (0.9564) loses to de-vigged
   Bet365 (0.9512) — and that test used *real* season-to-date features, which
   the live inference path does not produce. So "predict better than the market"
   is not a reachable strategy.
2. **Naive averaging helps only when components are weak and diverse.** Without
   odds the 6-model average beats every member. With odds it is worse than
   XGBoost alone — LR/SVM/LDA/RF are near-linear boundaries on the same scaled
   features, so they are echoes, not opinions.

### Walk-forward baseline board (authoritative)

Expanding-window CV, one fold per season, 16 folds per league, 19,760 matches.
Produced by `src/eval/backtest.py`; raw output in `data/processed/baseline_*.csv`.

| model | EPL logloss | vs mkt | ECE | La Liga logloss | vs mkt | ECE | beat mkt |
|---|---|---|---|---|---|---|---|
| **MARKET** | **0.9633** | — | 0.0289 | **0.9544** | — | 0.0247 | — |
| market+10%model | 0.9642 | +0.0009 | 0.0285 | 0.9542 | −0.0001 | 0.0264 | 5/16, 8/16 |
| market+25%model | 0.9686 | +0.0053 | 0.0305 | 0.9572 | +0.0028 | 0.0256 | 3/16, 6/16 |
| logistic_pit | 0.9961 | +0.0328 | 0.0322 | 0.9898 | +0.0355 | 0.0293 | 0/16 |
| strength_only | 1.0097 | +0.0463 | 0.0294 | 0.9994 | +0.0451 | 0.0232 | 0/16 |
| xgb_pit | 1.0231 | +0.0597 | 0.0501 | 1.0104 | +0.0561 | 0.0393 | 0/16 |
| xgb_pit_decay | 1.0560 | +0.0927 | 0.0721 | 1.0353 | +0.0809 | 0.0597 | 0/16 |
| base_rate | 1.0682 | +0.1048 | 0.0177 | 1.0599 | +0.1056 | 0.0153 | 0/16 |

### Dixon-Coles board

Same harness, same folds (`data/processed/baseline_dc_*.csv`):

| model | EPL logloss | vs mkt | ECE | La Liga logloss | vs mkt | ECE |
|---|---|---|---|---|---|---|
| **MARKET** | **0.9633** | — | 0.0289 | **0.9544** | — | 0.0247 |
| dc_goals (best half-life) | 0.9887 | +0.0254 | 0.0340 | 0.9734 | +0.0191 | 0.0298 |
| dc_shots (best half-life) | 1.0016 | +0.0383 | 0.0382 | 0.9864 | +0.0321 | 0.0396 |

- **Dixon-Coles on goals is the best model available**, displacing logistic
  regression, with calibration close to the market's and far better than XGB's.
- **Half-life is not a meaningful knob for DC.** 365/730/1460 all land within
  0.0012 of each other. EPL nominally prefers 365, La Liga 730; that is noise.
  Fix it at 365 and stop tuning it.
- **The shots variant is consistently worse than goals** — roughly +0.013 log
  loss in both leagues, same direction and magnitude. The xG-substitute does not
  pay off on 1X2. It is retained only if the walk-forward blend shows its errors
  are decorrelated enough to help.
- Still **no model beats the market**: the best managed 1/16 folds, worse than chance.

### Walk-forward blend board

Blend weights fitted on **prior folds only** (`data/processed/blend_*.csv`).
Sweeping weights on the test folds and reporting the best would be the same
maximum-selection bias that made the old parlay engine report +19.4% edges.

| model | EPL logloss | ECE | La Liga logloss | ECE |
|---|---|---|---|---|
| **MARKET** | **0.9633** | 0.0289 | **0.9544** | 0.0247 |
| market+dc (walk-forward weight) | 0.9638 | 0.0280 | 0.9545 | 0.0245 |
| dc_goals+shots (wf weight) | 0.9878 | 0.0342 | 0.9742 | 0.0301 |
| dc_goals | 0.9887 | 0.0340 | 0.9746 | 0.0286 |
| dc_goals_calibrated | 0.9923 | 0.0374 | 0.9761 | 0.0300 |
| dc_shots | 1.0016 | 0.0382 | 0.9873 | 0.0375 |

Decisions taken from this:

1. **Keep the shots variant at a walk-forward weight (~15-20%)**, but hold it
   lightly: it improves the model by 0.0009 (EPL) and 0.0004 (La Liga). Positive
   in both leagues, so directionally real, but close to a rounding error.
2. **Calibration is OFF by default for Dixon-Coles.** Temperature scaling made
   it worse on both log loss and ECE in both leagues. DC is already reasonably
   calibrated, so the layer adds noise rather than removing bias. Caveat: this
   used a single 80/20 chronological inner split, not the multi-fold
   `oof_calibrate`, so the calibration set came from a different era than the
   test season. Retest against the divergence probabilities in Phase 4, where
   inputs are blended and miscalibration is likelier.
3. **The market blend converged to zero model weight.** Free to choose any
   weight from prior seasons, the procedure started near 0.10 and selected
   **0.00 in both leagues** by the final fold. The strategy was not imposed —
   walk-forward selection discovered it.

Three findings that shape Phase 3:

1. **No standalone model beat the market in any of 32 fold-league combinations.**
   The blends are noise: 8/16 in La Liga is exactly a coin flip, and the
   aggregate difference is within ±0.001.
2. **Complexity actively hurts.** logistic > strength-only > XGB > XGB+decay.
   Every step up in sophistication scored worse. Phase 3 should start simple and
   add complexity only where the harness shows it paying.
3. **Time decay hurt and wrecked calibration.** A 730-day half-life pushed
   XGB's ECE from 0.0501 to 0.0721. Do not assume decay helps — fit the
   half-life, or drop it.

**Therefore the edge source is Kalshi-vs-sharp-line divergence**, not model
supremacy. De-vigged sharp consensus is fair value; the model supplies fair
value only where no sharp line exists.

Arm C (model-only) is retained as a **funded control expected to lose**. Its
losing is what makes arms A and B interpretable.

## Architecture

Four layers, each independently scoreable.

**Data** — football-data.co.uk `E0` + `SP1` (results and closing odds) ·
ClubElo API (`api.clubelo.com/YYYY-MM-DD`) · The Odds API (pre-match consensus,
free tier) · Understat (xG, both leagues) · Kalshi (prices, **read-only key**).

**Fair value** — de-vigged sharp consensus is the anchor. A time-decayed,
isotonic-calibrated Dixon-Coles on xG covers markets without a sharp line. The
two blend by a weight fitted **out-of-fold**, never hand-picked.

**Betting** — `edge = p_fair − kalshi_ask − fee(p)`, where
`fee(p) = max(0.01, ceil(0.07 · p · (1−p) · 100) / 100)` per contract.
Tuned minimum-edge threshold. Quarter-Kelly, **no floor**, hard cap 2–3%.

**Evaluation** — built before any model work. Walk-forward CV; log loss, Brier,
calibration curve, CLV, ROI with variance bands. Nothing gets funded without it.

## The experiment

Four books, $10,000 each, **no reset and no reload** for the season. Each pair
differs in exactly one variable.

| Arm | Edge source | Staking | Isolates |
|---|---|---|---|
| A | Divergence | Quarter-Kelly | flagship |
| B | Divergence | Flat 1% | A/B → staking rule |
| C | Model-only vs Kalshi | Quarter-Kelly | A/C → edge source |
| D | Parlay / SGP | Quarter-Kelly | parlays at all? |

An arm that busts is a real result and stays busted. Arm D is expected to be
the weakest — thin book, fees compounding per leg, and selection bias scaling
with the number of combinations enumerated. It is retained because a negative
result is still a result, and it is fake money.

**Primary metric is CLV, not P&L.** At ~150 bets per arm, P&L is almost
entirely variance; CLV converges far faster and is the only honest read by May.

## Scope

**Kalshi series tickers** (verified live against `/trade-api/v2/series`, 2026-08-02):

| market | EPL | La Liga |
|---|---|---|
| 1X2 | `KXEPLGAME` | `KXLALIGAGAME` |
| totals | `KXEPLTOTAL` | `KXLALIGATOTAL` |
| BTTS | `KXEPLBTTS` | `KXLALIGABTTS` |

**Trap: `KXLALIGA2*` is LaLiga 2, the second division** — `KXLALIGA2GAME`,
`KXLALIGA2TOTAL`, `KXLALIGA2BTTS` and friends. Any prefix match on `KXLALIGA`
silently pulls in second-division fixtures we have neither ratings nor sharp
lines for. Always match series tickers exactly, never by prefix.

As of 2026-08-02 all six series return zero open markets: the seasons start
2026-08-15 (La Liga) and 2026-08-21 (EPL), and Kalshi lists closer to kickoff.
End-to-end live validation is therefore blocked until markets appear.

**Markets:** 1X2, totals, BTTS. All three have sharp reference lines, so the
divergence strategy applies to every bet placed. Corners and player props are
excluded — no sharp anchor means model-only fair value, which the benchmark
above shows is the weakest part of the stack.

**Money:** entirely simulated. The Kalshi key is read-only and used for prices
only. No order-placement code path exists in the repo.

**Leagues:** EPL and La Liga. Champions League deferred until the draw is known.

## Automation

GitHub Actions, public repo, ledger committed back to a data branch.

- **Fri 10:00 UTC** — collect → price → stake → log
- **Mon 10:00 UTC** — settle → score → CLV report

Accepts the loss of ~5 midweek matchweeks out of 38 in exchange for a simple,
readable cycle.

**Settlement:** ESPN for same-day grading so the Monday report is timely,
reconciled against the football-data.co.uk weekly CSV, which is authoritative
and carries closing odds for CLV. Disagreements are flagged, not silently
resolved — undetected grading errors are exactly how this project would fool
itself for a whole season.

**LLM layer:** Magnus/Athena persist as commentary only. They never size or
select a bet.

## Phases

0. **Stop the bleeding** — club Elo, EPL/La Liga settlement, bet grading,
   delete every fabricated fallback, restructure ledger to 4 × $10k.
1. **Data foundation** — rebuild per-league from E0 + SP1 with real closing
   odds, backfill xG, canonicalise team names (41 case-collisions today).
2. **Eval harness** — walk-forward CV and the metric suite, plus a documented
   baseline board so later changes are measured against a fixed start.
3. **Model core** — xG Dixon-Coles per league, calibrated; market-residual GBM;
   OOF-fitted blend. The six existing models get a fair trial here and are kept
   or pruned on measured out-of-fold contribution, stacked rather than averaged.
4. **Betting engine** — fee-aware selection, the four arms, staking.
5. **Agentic automation** — orchestrator and subagents on the Fri/Mon cycle.

## Non-goals

- Beating Bet365 head-to-head. The benchmark says it does not happen.
- Real-money execution.
- Champions League, until the group stage draw is known.
- Corners and player-prop markets, unless a sharp reference source appears.
