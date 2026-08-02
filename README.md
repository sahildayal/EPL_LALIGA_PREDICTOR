# Football Betting Lab — EPL & La Liga, 2026/27

An automated paper-betting system that runs itself. Every week it prices Premier
League and La Liga fixtures against sharp bookmaker consensus, finds where the
Kalshi prediction market disagrees, stakes four competing strategies with
$10,000 of fake money each, and commits the result back to this repo.

At the end of the season one of those four strategies will have won, and the git
history will show it wasn't decided after the fact.

> **No real money, and no order placement.** Kalshi credentials are read-only,
> and there is no `POST /orders` code path anywhere in this repository — it was
> deleted rather than guarded, so no configuration mistake can make this real.

> The repo name is historical. This began as a 2026 World Cup predictor; that
> tournament is over and the system was rebuilt around club football.

---

## The finding that shapes everything

**No model beat the market.** Walk-forward cross-validation over 16 seasons in
two leagues found zero fold-league combinations where a standalone model beat
the de-vigged sharp line. When a market/model blend weight was fitted
walk-forward, it converged to **0.00 in both leagues**.

| Model | EPL log loss | La Liga log loss |
|---|---|---|
| **Market (de-vigged sharp)** | **0.9633** | **0.9544** |
| Dixon-Coles (goals) | 0.9887 | 0.9734 |
| Logistic regression | 0.9961 | 0.9898 |
| XGBoost | 1.0231 | 1.0104 |
| XGBoost + time decay | 1.0560 | 1.0353 |

Lower is better, and complexity hurt at every step. So this system doesn't try
to out-predict the market. It treats the sharp line as truth and hunts for
places where Kalshi disagrees with it. The model earns its keep only where no
sharp line exists.

---

## Quick start

```bash
git clone https://github.com/sahildayal/WorldCupPredictor.git
cd WorldCupPredictor
pip install -r requirements.txt

cp .env.example .env          # then fill in your keys
python -m src.data.dataset    # build the training set (~2 min, 19,760 matches)
python -m src.pipeline.run preflight
```

`preflight` proves your credentials and data sources work without placing
anything. You want `"ok": true` on all four checks.

### Credentials

```bash
ODDS_API_KEY=...                            # the-odds-api.com
KALSHI_API_KEY_ID=...                       # UUID from Kalshi's API keys page
KALSHI_PRIVATE_KEY_PATH=/path/to/kalshi.pem # local runs
```

In GitHub Actions, supply `KALSHI_PRIVATE_KEY_PEM` — the file's full contents,
including the `-----BEGIN/END-----` lines — so the key never touches the
runner's filesystem. The env var wins when both are set, so a stale local path
can't override a CI secret.

---

## How a matchweek works

```
Thursday 09:00 UTC   preflight  check credentials before it matters
Friday   09:00 UTC   stake      price the matchweek, place bets
Sat/Sun  11:00,14:00 snapshot   capture closing prices (read-only)
Tuesday  09:00 UTC   settle     grade results, void postponements, score
```

Run any of them by hand:

```bash
python -m src.pipeline.run stake --dry-run   # price and log, write nothing
python -m src.pipeline.run stake
python -m src.pipeline.run snapshot
python -m src.pipeline.run settle
python -m src.pipeline.run report            # current standings
```

**Why Friday morning.** Both leagues schedule Friday-night fixtures, so a
Friday-evening run would price part of the matchweek after it had started.

**Why Tuesday, not Monday.** A Monday-morning settle runs *before* Monday Night
Football, so every MNF bet would sit pending for another full week.

**Why the weekend snapshots.** Closing Line Value is the season's primary metric
— at ~150 bets per arm, P&L is mostly variance while CLV converges far faster.
But CLV only exists if the closing price is captured before the market resolves.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | clean run |
| 2 | completed, but a human should look (score dispute, unrecognised team) |
| 1 | failed — **no bets placed** |

Code 2 is the one that matters: a bet graded on a score ESPN and
football-data.co.uk disagree about must not look identical to a clean week.
Anything non-zero opens a GitHub issue labelled `matchweek-alert`, closed
automatically by the next clean run of that job.

**The pipeline fails closed.** If any required source is unavailable it places
zero bets and exits non-zero. There is no "bet the half we could price" path — a
missed matchweek costs a little sample size, while betting on stale or partial
prices costs money and corrupts the experiment the season exists to run.

---

## The four arms

Each starts with $10,000. No reloads — an arm that busts is done.

| Arm | Fair value from | Staking | What it isolates |
|---|---|---|---|
| **A** Divergence + quarter-Kelly | de-vigged sharp consensus | quarter-Kelly, 3% cap | the flagship |
| **B** Divergence + flat | de-vigged sharp consensus | flat 1% of starting bankroll | A vs B → the staking rule |
| **C** Model-only | Dixon-Coles | quarter-Kelly, 4% min edge | A vs C → the edge source |
| **D** Parlay / SGP | sharp consensus, compounded | flat 1% | does the parlay structure clear its own vig? |

**Arm C is expected to lose.** It's funded anyway, because without a control
that loses, "divergence works" and "we got lucky" look identical.

**Arm D is the subtle one.** Three things make parlays structurally hard, and
each is handled rather than assumed away:

- **Fees compound per leg** against a single payout. This is the main reason
  parlays lose.
- **Same-game legs are priced off the fitted Dixon-Coles score matrix**, never
  by multiplying correlated probabilities. Critically, the correlation
  multiplier is applied to *both* the joint probability and the synthetic ask.
  Applying it only to the numerator manufactures enormous fake edge — a bug this
  code had, and now has three regression tests against.
- **Legs are shrunk toward their ask before compounding.** Enumerating
  combinations and keeping the best selects for estimation error, and that bias
  multiplies across legs.

The combined ask is assumed to be the product of leg asks, which *flatters*
arm D, since a real quote would be worse. Every parlay records
`ask_is_synthetic` and pays a penalty for it.

---

## How an edge is found

1. **Sharp consensus** from The Odds API — Pinnacle preferred, median across
   Betfair/Smarkets/Matchbook otherwise.
2. **De-vig with Shin (1993)**, not proportional. Shin corrects the
   favourite-longshot bias, shading favourites up relative to naive
   normalisation.
3. **Kalshi ask** for the same selection.
4. **Net edge** = fair − ask − fee − derivation penalty. Kalshi's fee is
   `roundup_to_cent(0.07 × contracts × price × (1 − price))`, a far heavier tax
   on cheap contracts than on even-money ones.
5. Anything below the arm's threshold, or outside 5c–95c, is dropped. One bet
   per fixture per market, so correlated selections can't quietly concentrate
   risk beyond what the per-bet cap implies.

**BTTS is derived, not quoted.** The odds feed serves 1X2 and totals but not
BTTS, so the system solves for the `(λ_home, λ_away, ρ)` triple whose
Dixon-Coles scoreline distribution reproduces the sharp 1X2 *and* totals prices,
then reads BTTS off it. That's interpolation from prices the market already set,
not prediction — and if the fit doesn't reproduce those prices, the fixture
simply isn't bet.

Asian totals lines are handled explicitly: half lines (2.5) are a plain
threshold, integer lines (3.0) condition on no push, quarter lines (2.75) split
across the two halves.

---

## Repository layout

```text
src/
├── pipeline/
│   ├── run.py              CLI: stake | snapshot | settle | report | preflight
│   ├── matchweek.py        the three jobs, fail-closed
│   ├── results.py          ESPN results + football-data.co.uk reconciliation
│   └── kalshi_markets.py   exact series tickers, normalisation
├── market/
│   ├── edge.py             divergence pricing — the strategy in one module
│   ├── arms.py             the four arms
│   ├── parlay_arm.py       joint pricing, correlation, winner's-curse shrinkage
│   ├── staking.py          quarter-Kelly and flat, no minimum-stake floor
│   ├── fees.py             Kalshi's actual fee schedule
│   ├── grading.py          structured bets, tri-state grading
│   └── ledger.py           four arms, atomic writes, schema v3
├── models/
│   ├── dixon_coles.py      bivariate Poisson, low-score correction, time decay
│   ├── implied_goals.py    recover goal expectations from sharp prices
│   └── calibration.py      temperature scaling, isotonic
├── data/
│   ├── dataset.py          19,760 matches; one FeatureBuilder for train + serve
│   ├── odds_api.py         sharp consensus, Shin de-vig
│   └── canonical_teams.py  one name per club across six sources
└── eval/                   log loss, Brier, ECE, CLV, walk-forward backtest

scratch/            live test suite (321 tests, ~11s, fully offline)
scratch/legacy/     archived World Cup-era tests and scripts — never run
docs/AUTOMATION.md  operator manual: secrets, schedules, failure handling
```

---

## Design rules

These are load-bearing. Breaking one is how a ledger stops being trustworthy.

**Nothing invents data.** Every fabrication site from the original codebase now
raises instead — the synthetic training seed, demo parlay fixtures, a hardcoded
balance returned on an API *error*, two mock Kalshi payloads. An empty market
list means "do not bet", never "make something up".

**Grading is tri-state.** A bet that can't be graded raises `UngradeableBet` and
stays pending. It is never resolved as a loss. The previous grader matched
substrings, so "Da**rwin** Nunez to Score in Liverpool vs Arsenal" was graded
purely on whether Liverpool won, and corners, to-advance and anytime legs fell
through every branch to a silent LOSS.

**Bets are structured, never parsed.** `Bet.label` is for humans and is never
read back.

**Disagreements are reported, never auto-applied.** When ESPN and
football-data.co.uk disagree on a score, the run exits 2 and raises an issue.
Rewriting a settled bet from a scraper disagreement is how a public ledger stops
being credible.

**Arms are never reloaded.** Insufficient bankroll stops an arm; it doesn't top
it up.

**The ledger is tracked, and the bot commits it.** A public, timestamped git
history is what makes the season's result credible — results can't be quietly
revised afterwards. Schema migrations are strictly additive; anything that would
reinterpret an existing record raises instead.

---

## Testing

```bash
pytest              # 321 tests, ~11s, no network, no credentials
```

Scope lives in `pytest.ini`, so a bare `pytest` means the same thing locally as
in CI — when the two differ, the local one is what you start trusting. Archived
World Cup-era tests in `scratch/legacy/` are excluded; they hit live feeds and
assert pre-rebuild behaviour. See that directory's README.

Dependency majors are capped in `requirements.txt`. That isn't fussiness: this
pipeline runs unattended and fails closed, so an upstream major release doesn't
arrive as a deprecation warning — it arrives as a matchweek with zero bets
placed. It has already happened once, when pandas 3.0 removed
`to_numeric(errors="ignore")`.

---

## Legacy CLI

`main.py` and `src/predictor.py` hold the pre-rebuild multi-model ensemble —
Elo, Dixon-Coles and six ML classifiers — still useful for ad-hoc questions:

```bash
python main.py predict "Arsenal vs Chelsea"
```

**It is not on the betting path.** The weekly automation never imports it, and
no number it prints is an edge. The board at the top of this README is why.

---

## Status

Rebuilt and automated ahead of the 2026/27 season. La Liga opens 2026-08-15 and
the Premier League 2026-08-21, so the first live `stake` run is Friday
2026-08-14. Champions League is deferred until the draw is known.
