# Legacy: 2026 World Cup era

Archived tests and scripts from before the 2026/27 club-season rebuild.
**Nothing here runs in CI, and nothing here is maintained.**

## Why they were quarantined rather than deleted

They are the record of how the project worked before the rebuild, and a few
still describe behaviour worth remembering. But they cannot gate anything:

* **They hit live feeds.** Several call ESPN, football-data and news scrapers
  directly with no mocking. `test_cli_integration.py` alone takes 45 seconds.
  A test that only passes with a working network and live credentials cannot
  gate a deploy.
* **They assert behaviour the rebuild deliberately removed.** Three files were
  deleted outright rather than moved here, because they encoded requirements
  that are now actively wrong — see below.
* **A red suite nobody intends to fix stops being read.** That is the failure
  mode this directory exists to prevent.

Their paths are now one directory deeper, so `Path(__file__).parents[1]`
references inside them no longer resolve to the project root. They are archived,
not merely disabled. Treat them as history.

## Deleted, not archived

Three files asserted things that are now false by design:

| File | Asserted | Reality |
|---|---|---|
| `test_dashboard_existence.py` | `dashboard.html` exists with World Cup bracket elements | the browser dashboard was deliberately removed (commit `1d69933`) |
| `test_confederation_calibration.py` | `predict_match` applies CONMEBOL +50 / AFC −20 Elo boosts | confederations do not exist in club football; the code was removed in the club migration |
| `test_integration.py` | `paper_trading.update_bet` returns `placed` | that module is deliberately disabled — its substring grader mis-resolved player props as moneylines and booked corners legs as automatic losses |

Keeping tests that demand the return of a disabled grader would be worse than
useless: they would pressure a future change to re-enable the exact code path
that corrupted the old ledger.

## What replaced them

The live suite is in `scratch/` (14 files, 318 tests, ~17s, fully offline).
It covers the code that actually runs unattended each week: dataset
construction, de-vigging, Dixon-Coles, calibration, staking, edge, the four
arms, grading, the ledger, results collection and the pipeline jobs.

## `generate_mock_debates.py`

Kept here for history only. It fabricated debate content, and the rebuild's
standing rule is that no component may invent data it did not observe — every
former fabrication site now raises instead. Do not reintroduce it.
