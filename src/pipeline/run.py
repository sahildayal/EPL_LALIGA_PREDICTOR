"""
CLI entry point for the scheduled matchweek jobs.

    python -m src.pipeline.run stake     [--dry-run]   Fri 09:00 UTC
    python -m src.pipeline.run snapshot                Sat/Sun pre-kickoff
    python -m src.pipeline.run settle                  Tue 09:00 UTC
    python -m src.pipeline.run review                  after settle; advisory only
    python -m src.pipeline.run report                  read-only standings
    python -m src.pipeline.run preflight                credentials + data sources

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
from datetime import datetime, timedelta, timezone

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


#: Odds API credits a week of scheduled runs spends: 3 stakes + 6 scheduled
#: snapshots, each pricing two leagues at h2h+totals for one bookmaker group.
#: Closer-dispatched snapshots run --closing-only and cost nothing.
ODDS_CREDITS_PER_WEEK = (3 + 6) * 2 * 2


def _odds_credits_until_reset(now) -> int:
    """Credits the scheduled runs will spend between now and the 1st of next month."""
    first = (now.replace(day=1) + timedelta(days=32)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)
    days = (first - now).total_seconds() / 86400
    return int(ODDS_CREDITS_PER_WEEK * days / 7 + 0.999)


def preflight() -> dict:
    """
    Proves every credential and data source works, without needing live fixtures.

    This exists because `stake` collects Kalshi markets FIRST and fails closed if
    none are listed — so out of season, or on any week Kalshi has not posted the
    fixtures, the run aborts before the Odds API is ever contacted. A credential
    could be wrong for months and look identical to "no markets yet".

    Every check reports its own outcome. Nothing here places, prices or writes
    anything, so it is safe to run at any time.
    """
    checks, ok = {}, True

    # Kalshi: an authenticated call. A 200 with zero markets is a PASS — it means
    # the signature verified and there simply are no fixtures listed.
    try:
        from src.market.kalshi_client import KalshiClient
        from src.pipeline import kalshi_markets as km
        client = KalshiClient()
        if client.credentials_missing:
            raise RuntimeError("no usable credentials (see the warning above)")
        tickers = km.all_series_tickers()
        resp = client._request("GET", "/trade-api/v2/markets",
                               params={"series_ticker": tickers[0],
                                       "status": "open", "limit": 1})
        if resp.status_code == 200:
            checks["kalshi"] = {
                "ok": True,
                "credential_source": client.credential_source,
                "series_checked": tickers[0],
                "open_markets_seen": len(resp.json().get("markets", [])),
                "note": "authenticated; zero markets is expected out of season",
            }
        else:
            raise RuntimeError(f"HTTP {resp.status_code} — signature or key ID rejected")
    except Exception as exc:
        ok = False
        checks["kalshi"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # The Odds API: a free probe that does not consume quota.
    try:
        from src.data.odds_api import quota_remaining
        remaining = quota_remaining()
        checks["odds_api"] = {"ok": True, "requests_remaining": remaining}
        # The pool resets at the start of each month (500 on 1 Oct after 60 on
        # 24 Sep). Fail preflight, so it raises an alert, when what is left will
        # not last until then. On 15 Oct it read 152, then ran dry three days later.
        need = _odds_credits_until_reset(datetime.now(timezone.utc))
        checks["odds_api"]["needed_until_reset"] = need
        if remaining is not None and remaining < need:
            ok = False
            checks["odds_api"]["ok"] = False
            checks["odds_api"]["error"] = (
                f"{remaining} credits left but ~{need} needed before the monthly "
                "reset. Find what is spending them (logs record "
                "odds_quota_remaining) or swap ODDS_API_KEY.")
    except Exception as exc:
        ok = False
        checks["odds_api"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # The training dataset, which arm C needs and which CI rebuilds each Friday.
    try:
        from pathlib import Path
        import pandas as pd
        path = Path("data/processed/matches.csv")
        if not path.exists():
            raise FileNotFoundError(f"{path} missing; run `python -m src.data.dataset`")
        df = pd.read_csv(path, parse_dates=["date"])
        checks["dataset"] = {"ok": True, "matches": len(df),
                             "latest": str(df.date.max().date()),
                             "leagues": sorted(df.league.unique())}
    except Exception as exc:
        ok = False
        checks["dataset"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # The ledger: readable, right schema, four funded arms.
    try:
        from src.market import ledger
        state = ledger.load_state()
        checks["ledger"] = {
            "ok": True, "schema": state["schema_version"], "season": state["season"],
            "arms": {a: round(b["bankroll"], 2) for a, b in state["arms"].items()},
        }
    except Exception as exc:
        ok = False
        checks["ledger"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # Anthropic: powers the post-settle weekly review only (Phase 6a) — advisory
    # and never on the betting path. Deliberately does NOT affect the overall
    # `ok` verdict: the review already degrades to a silent skip when the key is
    # absent, so failing preflight over it would raise an alert for something
    # that was never going to block a bet.
    try:
        import os
        if not os.getenv("ANTHROPIC_API_KEY"):
            checks["anthropic"] = {"ok": False, "note": "unset — weekly review will be skipped"}
        else:
            import anthropic
            resp = anthropic.Anthropic().messages.create(
                model="claude-haiku-4-5", max_tokens=8,
                messages=[{"role": "user", "content": "Say OK."}])
            checks["anthropic"] = {"ok": resp.stop_reason != "refusal",
                                   "model": resp.model}
    except Exception as exc:
        checks["anthropic"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return {"job": "preflight", "ok": ok, "checks": checks}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.pipeline.run",
        description="Scheduled matchweek jobs for the four-arm paper season.")
    parser.add_argument("job", choices=("stake", "snapshot", "settle", "report",
                                        "preflight", "review"))
    parser.add_argument("--dry-run", action="store_true",
                        help="stake only: price and log the plan, write nothing")
    parser.add_argument("--closing-only", action="store_true",
                        help="snapshot only: stamp closing prices, skip the Odds API")
    parser.add_argument("--verbose", action="store_true",
                        help="print full run details to stdout")
    args = parser.parse_args(argv)

    if args.job == "preflight":
        report = preflight()
        print(json.dumps(report, indent=2, default=str))
        return EXIT_OK if report["ok"] else EXIT_FAILED

    if args.job == "review":
        from src.pipeline.review import run_review
        report = run_review()
        print(report.text if report.ok else f"REVIEW FAILED: {report.error}")
        # Advisory only: a broken review must never fail the workflow that also
        # commits the ledger. ok=False still exits 0.
        return EXIT_OK

    if args.job == "report":
        from src.market import ledger
        print(json.dumps(ledger.season_summary(), indent=2, default=str))
        return EXIT_OK

    if args.job == "stake":
        report = matchweek.run_stake(dry_run=args.dry_run)
    elif args.job == "snapshot":
        report = matchweek.run_snapshot(closing_only=args.closing_only)
    else:
        report = matchweek.run_settle()

    return _emit(report, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
