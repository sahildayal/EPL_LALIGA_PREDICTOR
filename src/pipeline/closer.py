"""
Triggers a snapshot shortly before every held bet's kickoff.

CLV is the metric this season is judged on, and it only exists if a price is
captured just before kickoff. The fixed-time snapshots could not do that:
GitHub starts scheduled jobs hours late (median 2.7h for snapshots this season,
up to 3.9h, and ~5h for settle), so the "Friday 18:00" run landed after
Friday-night kickoffs and Monday's after Monday-night games. By 2026-09-25 arms
A and B had a valid closing price on 0 of their 4 settled bets.

This job does not trust the clock. It wakes every few minutes, reads the
ledger as committed on main, and when a held bet's kickoff is LEAD away it
dispatches the snapshot workflow, whose start latency is seconds rather than
hours. The snapshot does the stamping, so there is exactly one code path that
writes closing prices, and it already refuses anything seen after kickoff.

Stdlib only, so the workflow needs no dependency install.

    python -m src.pipeline.closer [--budget-min 345] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEDGER = "data/processed/season_ledger.json"

#: How long before kickoff to trigger the snapshot. Covers dispatch latency,
#: the runner's dependency install and a queue behind a running stake or
#: settle (they share a concurrency group) with room to spare.
LEAD = timedelta(minutes=20)

#: Longest the loop sleeps without re-reading the ledger, so bets a stake run
#: adds while this job is alive are picked up.
POLL = timedelta(minutes=10)


def _ts(raw):
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def held_kickoffs(state: dict) -> set:
    """Every kickoff that an open single or an open parlay leg depends on."""
    out = set()
    for book in (state.get("arms") or {}).values():
        for bet in book.get("active_bets", []):
            k = _ts(bet.get("kickoff"))
            if k:
                out.add(k)
        for parlay in book.get("active_parlays", []):
            for leg in parlay.get("legs", []):
                k = _ts(leg.get("kickoff"))
                if k:
                    out.add(k)
    return out


def plan(kickoffs: set, now: datetime, done: set, lead: timedelta = LEAD):
    """
    Returns (due, next_due).

    `due` are kickoffs whose snapshot should fire now: inside the lead window
    and not yet started. A kickoff whose window opened while no closer was
    running is still due, so a late start costs precision, never the close.
    `next_due` is when the soonest future window opens, or None.
    """
    due = sorted(k for k in kickoffs if k not in done and k - lead <= now < k)
    ahead = [k - lead for k in kickoffs if k not in done and k - lead > now]
    return due, (min(ahead) if ahead else None)


def _read_ledger() -> dict:
    """The ledger as committed on main right now, not as checked out."""
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], check=True, timeout=60)
        raw = subprocess.run(["git", "show", f"origin/main:{LEDGER}"],
                             check=True, capture_output=True, timeout=30).stdout
        return json.loads(raw)
    except Exception as exc:                                      # noqa: BLE001
        print(f"[closer] could not read origin/main ({exc}); using the local copy")
        return json.loads(Path(LEDGER).read_text(encoding="utf-8"))


def _dispatch(dry_run: bool) -> bool:
    if dry_run:
        print("[closer] dry run: would dispatch snapshot.yml")
        return True
    r = subprocess.run(["gh", "workflow", "run", "snapshot.yml"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"[closer] dispatch failed: {r.stderr.strip()}")
    return r.returncode == 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=int, default=345,
                    help="stop after this many minutes (the runner hard limit is 360)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    deadline = datetime.now(timezone.utc) + timedelta(minutes=args.budget_min)
    done: set = set()
    while True:
        now = datetime.now(timezone.utc)
        if now >= deadline:
            print("[closer] budget spent; the next scheduled closer takes over")
            return 0
        due, next_due = plan(held_kickoffs(_read_ledger()), now, done)
        if due:
            names = ", ".join(k.strftime("%a %H:%M") for k in due)
            if _dispatch(args.dry_run):
                print(f"[closer] {now:%H:%M} snapshot dispatched for kickoff(s) {names}")
                done.update(due)
            else:
                time.sleep(60)         # back off rather than spin on a failing API
            continue
        if next_due is None or next_due >= deadline:
            # Nothing held kicks off inside this job's budget. Exit rather than
            # idle: the next scheduled closer starts within a couple of hours,
            # and every stake run dispatches one after placing bets.
            print("[closer] nothing to close inside the budget; exiting")
            return 0
        wake = min(next_due, now + POLL, deadline)
        time.sleep(max(1.0, (wake - now).total_seconds()))


if __name__ == "__main__":
    raise SystemExit(main())
