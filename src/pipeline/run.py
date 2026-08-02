"""
CLI entry point for the scheduled matchweek jobs.

    python -m src.pipeline.run stake     [--dry-run]   Fri 09:00 UTC
    python -m src.pipeline.run snapshot                Sat/Sun pre-kickoff
    python -m src.pipeline.run settle                  Tue 09:00 UTC
    python -m src.pipeline.run report                  read-only standings

Exit codes are the contract with GitHub Actions, and they distinguish three
states that a plain pass/fail would flatten:

    0  clean run
    2  the job completed but something needs a human (score mismatch between
       sources, unrecognised team names, markets that could not be priced)
    1  the job failed and NO bets were placed

2 is the important one. A settle that silently graded a bet on a disputed score
would otherwise look identical to a clean week.
"""
import argparse
import json
import sys

from src.pipeline import matchweek

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_WARN = 2


def _emit(report, verbose: bool) -> int:
    payload = {
        "job": report.job,
        "started_utc": report.started_utc,
        "ok": report.ok,
        "errors": report.errors,
    }
    if verbose:
        payload["details"] = report.details
    else:
        # Keep the default log readable: counts, not every bet. The full detail
        # is written to data/processed/matchweek_logs regardless.
        payload["summary"] = {k: v for k, v in report.details.items()
                              if not isinstance(v, (list, dict))}
    print(json.dumps(payload, indent=2, default=str))

    if not report.ok:
        return EXIT_FAILED
    return EXIT_WARN if report.errors else EXIT_OK


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.pipeline.run",
        description="Scheduled matchweek jobs for the four-arm paper season.")
    parser.add_argument("job", choices=("stake", "snapshot", "settle", "report"))
    parser.add_argument("--dry-run", action="store_true",
                        help="stake only: price and log the plan, write nothing")
    parser.add_argument("--verbose", action="store_true",
                        help="print full run details to stdout")
    args = parser.parse_args(argv)

    if args.job == "report":
        from src.market import ledger
        print(json.dumps(ledger.season_summary(), indent=2, default=str))
        return EXIT_OK

    if args.job == "stake":
        report = matchweek.run_stake(dry_run=args.dry_run)
    elif args.job == "snapshot":
        report = matchweek.run_snapshot()
    else:
        report = matchweek.run_settle()

    return _emit(report, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
