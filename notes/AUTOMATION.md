# Weekly automation

The season runs itself on three scheduled GitHub Actions workflows. This
document is the operator's manual: what runs when, what to put in secrets, how
to read a failure, and what to do about it.

## The cycle

| Day | Time (UTC) | Job | Writes | Workflow |
|---|---|---|---|---|
| Friday | 09:00 | `stake` | places the matchweek's bets | `stake.yml` |
| Friday | 18:00 | `snapshot` | stamps closing prices for Friday-night fixtures | `snapshot.yml` |
| Sat & Sun | 11:00, 14:00 | `snapshot` | stamps closing prices for CLV | `snapshot.yml` |
| Monday | 20:00 | `snapshot` | stamps closing prices before Monday-night football | `snapshot.yml` |
| Tuesday | 09:00 | `settle` | grades results, voids postponements | `settle.yml` |

All three call the shared body in `_matchweek.yml`, so checkout, credentials,
the ledger commit and the alerting logic exist in exactly one place.

**Why these times.**

* **Friday 09:00** sits ahead of the earliest kickoff. Both leagues schedule
  Friday-night fixtures (20:00 UK / 21:00 CET), so a Friday-evening run would
  price part of the matchweek after it had already started.
* **The snapshots** exist solely for Closing Line Value. CLV is the season's
  primary metric — at roughly 150 bets per arm, P&L is mostly variance while CLV
  converges far faster — but it only exists if the closing price is captured
  before the market resolves. Two weekend runs per day: one near the main
  kickoff blocks, one as insurance.

  The Friday 18:00 and Monday 20:00 runs were added after the EPL's opening
  weekend, where a weekend-only cadence left a third of that week's bets with a
  missing or meaningless closing price. Real Betis v Real Sociedad kicked off
  Friday 22:00 UTC, thirteen hours before the first snapshot, so it was never
  stamped at all; Monday-night fixtures were stamped from the Sunday 14:00 run
  and settled Tuesday, recording a price ~32 hours early as the close. Both
  leagues schedule Friday-night fixtures every week — which is the very reason
  `stake` runs Friday morning — so neither was a one-off.

  A price observed after kickoff is refused outright. Kalshi can leave a market
  open into the match, and stamping an in-play price would not merely lose CLV
  for that bet, it would overwrite a good earlier stamp with a worse number and
  report it as the close.
* **Tuesday 09:00, not Monday.** A Monday-morning settle runs *before* Monday
  Night Football, so every MNF bet would sit pending for another full week. One
  day of reporting latency buys a complete matchweek.

Cron is UTC year-round while the leagues run on local time, so these fire an
hour "later" in local terms once the clocks change. The margins are wide enough
that it never matters.

## Setup

### Secrets

Repository → Settings → Secrets and variables → Actions:

| Secret | What it is |
|---|---|
| `ODDS_API_KEY` | the-odds-api.com key, for the sharp consensus line |
| `KALSHI_API_KEY_ID` | Kalshi API key ID |
| `KALSHI_PRIVATE_KEY_PEM` | the **contents** of your Kalshi RSA private key |
| `ANTHROPIC_API_KEY` | *(optional — see Weekly review, below)* |

Paste the PEM in full, `-----BEGIN…` through `-----END…`, newlines included.
The client reads it from the environment and loads it in memory; it is never
written to the runner's filesystem, so nothing else in the job can read it off
disk. Locally, `KALSHI_PRIVATE_KEY_PATH` in `.env` still works — the env var
wins when both are set, so a stale local path cannot override a CI secret.

The repo is public. `.env` is gitignored; keep it that way, and treat any key
that lands in a commit as burned.

### Permissions

`Settings → Actions → General → Workflow permissions` must be **Read and write**.
The jobs commit the ledger and open alert issues; with read-only permissions
every run fails at the commit step after doing all its work.

### Weekly review (optional, currently off)

`src/pipeline/review.py` asks Haiku for a short plain-English summary after
each settle — which arm is ahead, what CLV shows, anything needing a human —
and posts it to a running "Weekly review" issue. It is read-only: it never
prices, stakes, or writes to the ledger.

**Left dormant on purpose.** It needs `ANTHROPIC_API_KEY` — an Anthropic
*Developer API* key from console.anthropic.com, billed separately from a
Claude Pro subscription, which cannot authorize an unattended script. Without
the secret, the workflow step prints `ANTHROPIC_API_KEY not set; skipping` and
exits clean, and `preflight` reports it unset without failing the check — the
rest of the pipeline is completely unaffected either way. To turn it on later,
set the secret; there is nothing else to change.

## Where state lives

`data/processed/season_ledger.json` is deliberately tracked, and the bot commits
it back to `main` after every run. A public, timestamped git history is what
makes the season's result credible: results cannot be quietly revised after the
fact. The per-run detail lands in `data/processed/matchweek_logs/` and is also
uploaded as a workflow artifact (30 days).

Bot commits carry `[skip ci]` and the test workflow ignores those paths, so the
weekly ledger churn does not trigger a test run.

Concurrency group `matchweek-ledger` serialises **all** matchweek jobs, not each
job against itself. Stake and snapshot can otherwise overlap on a Saturday, and
the ledger is a non-atomic read-modify-write.

## Exit codes

The CLI distinguishes three states that a plain pass/fail would flatten:

| Code | Meaning | What the workflow does |
|---|---|---|
| 0 | clean run | commits, closes any open alert issue |
| 2 | completed, but a human should look | commits, opens/updates an alert issue |
| 1 | failed — **no bets were placed** | no commit, opens/updates an alert issue, run marked failed |

Code 2 is the one that matters. A settle that graded a bet on a score ESPN and
football-data.co.uk disagree about would otherwise look identical to a clean
week.

## Failure handling

Every non-clean run opens (or comments on) a GitHub issue labelled
`matchweek-alert`, and a later clean run of the same job closes it. A skipped
matchweek is a data-loss event for the experiment, so it gets a durable in-repo
record rather than an email that gets filtered away.

**The pipeline fails closed.** If any required data source is unavailable the
run places zero bets and exits non-zero. There is no "bet the half we could
price" path: a missed matchweek costs a little sample size, while betting on
stale or partial prices costs money and corrupts the experiment.

Common causes:

| Symptom | Cause | Fix |
|---|---|---|
| `KalshiUnavailable` | credentials wrong, or no in-scope markets listed yet | check secrets; early season, Kalshi may not have posted the fixtures |
| `OddsUnavailable` | Odds API quota exhausted or key rotated | check quota; `stake` uses ~2 calls/week |
| `SCORE MISMATCH` (exit 2) | ESPN and football-data.co.uk disagree | settle used the ESPN score; review the named fixtures manually |
| `unrecognised team names` (exit 2) | a promoted club missing from `canonical_teams` | add the alias, then re-run `settle` — the 10-day lookback picks it up |
| push step fails | workflow permissions are read-only | set Read and write |

A missed `settle` is self-healing: the results lookback is ten days, so the next
Tuesday picks up everything the skipped run would have handled. A missed `stake`
is not — that matchweek simply has no bets, which is the intended behaviour.

## Running by hand

```bash
python -m src.pipeline.run stake --dry-run   # price and log, write nothing
python -m src.pipeline.run stake
python -m src.pipeline.run snapshot
python -m src.pipeline.run settle
python -m src.pipeline.run report            # read-only standings
```

Add `--verbose` to print the full run detail rather than the counts.

All three scheduled workflows also accept `workflow_dispatch`, so you can run
any of them from the Actions tab. `stake` takes a `dry_run` input, which
suppresses the ledger commit as well as the staking — otherwise "dry" would be
a lie.

## The four arms

Each gets $10,000 of fake money. Every real Kalshi credential is used for
**reading prices only**; there is no order-placement code path in this repo.

| Arm | Strategy | Fair value from | Staking |
|---|---|---|---|
| A | Divergence, flagship | de-vigged sharp consensus | quarter-Kelly |
| B | Divergence | de-vigged sharp consensus | flat 1% of starting bankroll |
| C | Model-only control | Dixon-Coles | quarter-Kelly, wider threshold |
| D | Parlay / SGP | sharp consensus, compounded | flat 1% |

A vs B isolates the staking rule. A vs C isolates the edge source. C is expected
to lose — walk-forward CV found no model beating the market in any of 32
fold-league combinations — and is funded anyway, because without a control that
loses, "divergence works" and "we got lucky" look identical.

D answers whether the parlay *structure* clears its own compounded vig. Its legs
are drawn at a lower bar than arm A's betting threshold on purpose: requiring
each leg to be independently bettable would make D a near-duplicate of A's
selections and answer a different question. Two caveats are recorded on every
parlay rather than assumed away:

* the combined ask is the **product of leg asks**, which is optimistic — a real
  quote would be worse — so `ask_is_synthetic` is stamped on every record and a
  penalty is charged against the edge;
* same-game legs are priced off the fitted Dixon-Coles score matrix, not by
  multiplying correlated probabilities. Without a matrix for that fixture, arm D
  refuses to price the parlay at all.

## What is deliberately absent

There is no order placement. The user's Kalshi access is read-only and the
order-placement path was deleted rather than guarded, so no configuration
mistake can turn a paper season into a real one.
