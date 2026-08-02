"""
Match results for settlement, from two sources that check each other.

ESPN's scoreboard is fast and available minutes after full time, which is what
the Tuesday settle job needs. It is also a live-ops feed: scores are occasionally
corrected, and its team naming drifts. football-data.co.uk publishes the same
fixtures a few days later as a curated CSV that is effectively the archival
record for these two leagues.

So we settle on ESPN and **reconcile against football-data** on the following
run. A disagreement is never resolved silently — it is reported, because a score
correction after settlement means a bet was graded on a wrong number, and that
is exactly the class of quiet error the rebuild exists to remove.

Postponements are treated as first-class. A postponed or abandoned fixture does
not produce a result; it produces a VOID instruction, and the stake comes back.
"""
import io
from datetime import datetime, timedelta, timezone

import requests

from src.data.canonical_teams import canonical, UnknownTeam
from src.market.grading import MatchResult

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Referer": "https://www.espn.com/soccer/scoreboard/",
}

# Only the two leagues in scope. The old settlement path iterated six leagues
# including three that had no bets, which cost requests and hid failures.
ESPN_LEAGUES = {"epl": "eng.1", "laliga": "esp.1"}
FOOTBALL_DATA_CODES = {"epl": "E0", "laliga": "SP1"}
FOOTBALL_DATA_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"

# ESPN status names that mean "this fixture will not produce a result".
VOID_STATUSES = {
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "cancelled",
    "STATUS_CANCELLED": "cancelled",
    "STATUS_ABANDONED": "abandoned",
    "STATUS_SUSPENDED": "suspended",
    "STATUS_FORFEIT": "forfeit",
}

LOOKBACK_DAYS = 10


class ResultsUnavailable(RuntimeError):
    """Raised when the results feed cannot be reached. Settlement must not proceed."""


def _get(url: str, params: dict = None, timeout: int = 20):
    try:
        resp = requests.get(url, params=params, headers=ESPN_HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise ResultsUnavailable(f"{url}: {exc}") from exc
    if resp.status_code != 200:
        raise ResultsUnavailable(f"{url} returned {resp.status_code}")
    return resp


def _parse_event(event: dict) -> dict:
    """
    Turns one ESPN event into a normalised record, or None if it is unusable.

    Returns {'kind': 'result'|'void'|'pending', ...}. Unknown team names are
    surfaced rather than dropped: a fixture we cannot name is a fixture we cannot
    settle, and silently skipping it would leave bets pending forever with no
    explanation.
    """
    comps = event.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    status = ((comp.get("status") or event.get("status") or {}).get("type") or {})
    name = status.get("name", "")

    sides = {}
    for c in comp.get("competitors", []):
        team = (c.get("team") or {}).get("displayName") or (c.get("team") or {}).get("name")
        if not team:
            return None
        sides[c.get("homeAway")] = (team, c.get("score"))
    if "home" not in sides or "away" not in sides:
        return None

    try:
        home = canonical(sides["home"][0], strict=True)
        away = canonical(sides["away"][0], strict=True)
    except UnknownTeam as exc:
        return {"kind": "unknown_team", "detail": str(exc),
                "raw": [sides["home"][0], sides["away"][0]]}

    if name in VOID_STATUSES:
        return {"kind": "void", "home": home, "away": away,
                "reason": VOID_STATUSES[name], "event_id": event.get("id")}

    if not status.get("completed"):
        return {"kind": "pending", "home": home, "away": away, "status": name}

    try:
        hg, ag = int(sides["home"][1]), int(sides["away"][1])
    except (TypeError, ValueError):
        # Marked complete but without a usable score. Refusing to invent one.
        return {"kind": "pending", "home": home, "away": away,
                "status": f"{name} (no score)"}

    return {"kind": "result", "home": home, "away": away,
            "home_goals": hg, "away_goals": ag,
            "date": (event.get("date") or "")[:10], "event_id": event.get("id")}


def fetch_espn(days_back: int = LOOKBACK_DAYS, today=None) -> dict:
    """
    Sweeps the ESPN scoreboard over a lookback window.

    The window matters more than it looks: it must cover a Friday fixture settled
    the following Tuesday, and a fixture postponed and replayed midweek. Ten days
    is one request per league per day and cheap.

    Raises ResultsUnavailable if EVERY request fails — a total feed outage must
    stop settlement rather than silently settle nothing.
    """
    today = today or datetime.now(timezone.utc).date()
    results, voids, pending, unknown = {}, {}, [], []
    ok, failed = 0, 0

    for league in ESPN_LEAGUES.values():
        for offset in range(-days_back, 1):
            date_str = (today + timedelta(days=offset)).strftime("%Y%m%d")
            try:
                resp = _get(f"{ESPN_BASE}/{league}/scoreboard", {"dates": date_str})
                events = resp.json().get("events", [])
            except (ResultsUnavailable, ValueError):
                failed += 1
                continue
            ok += 1
            for event in events:
                rec = _parse_event(event)
                if not rec:
                    continue
                if rec["kind"] == "unknown_team":
                    unknown.append(rec)
                    continue
                key = (rec["home"], rec["away"])
                if rec["kind"] == "result":
                    results[key] = rec
                elif rec["kind"] == "void":
                    # A later result supersedes an earlier postponement (the
                    # fixture was replayed inside the window).
                    if key not in results:
                        voids[key] = rec
                else:
                    pending.append(rec)

    if ok == 0:
        raise ResultsUnavailable(
            f"All {failed} ESPN scoreboard requests failed; refusing to settle on no data.")

    # A fixture that was postponed and has since been played is not a void.
    voids = {k: v for k, v in voids.items() if k not in results}
    return {"results": results, "voids": voids, "pending": pending,
            "unknown_teams": unknown, "requests_ok": ok, "requests_failed": failed}


# --- Reconciliation ----------------------------------------------------------

def _season_code(today=None) -> str:
    """football-data season code, e.g. '2627' for the 2026/27 season."""
    today = today or datetime.now(timezone.utc).date()
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def fetch_football_data(season: str = None) -> dict:
    """
    Current-season results from football-data.co.uk, keyed (home, away).

    Returns {} on any failure. This is the reconciliation source, not the
    settlement source: its absence must degrade the check, never block the run.
    """
    import pandas as pd
    season = season or _season_code()
    out = {}
    for league, code in FOOTBALL_DATA_CODES.items():
        try:
            resp = _get(FOOTBALL_DATA_URL.format(season=season, code=code))
            df = pd.read_csv(io.StringIO(resp.text), encoding_errors="ignore")
        except Exception:
            continue
        for _, row in df.iterrows():
            try:
                home = canonical(str(row["HomeTeam"]), strict=True)
                away = canonical(str(row["AwayTeam"]), strict=True)
                hg, ag = int(row["FTHG"]), int(row["FTAG"])
            except (KeyError, UnknownTeam, TypeError, ValueError):
                continue
            corners = None
            try:
                corners = int(row["HC"]) + int(row["AC"])
            except (KeyError, TypeError, ValueError):
                pass
            out[(home, away)] = {"home": home, "away": away, "home_goals": hg,
                                 "away_goals": ag, "corners": corners,
                                 "league": league}
    return out


def reconcile(espn_results: dict, archive: dict) -> dict:
    """
    Compares what we settled on against the archival record.

    A mismatch means a bet was graded on a score that has since changed. We do
    NOT auto-correct: rewriting a settled bet from a scraper disagreement is how
    a ledger stops being trustworthy. It is reported for a human decision.
    """
    mismatches, confirmed, unseen = [], 0, []
    for key, espn in espn_results.items():
        ref = archive.get(key)
        if ref is None:
            unseen.append({"fixture": list(key), "note": "not yet published by football-data"})
            continue
        if (espn["home_goals"], espn["away_goals"]) == (ref["home_goals"], ref["away_goals"]):
            confirmed += 1
        else:
            mismatches.append({
                "fixture": list(key),
                "espn": [espn["home_goals"], espn["away_goals"]],
                "football_data": [ref["home_goals"], ref["away_goals"]],
            })
    return {"confirmed": confirmed, "mismatches": mismatches,
            "awaiting_archive": unseen}


# --- Public entry point ------------------------------------------------------

def collect(days_back: int = LOOKBACK_DAYS, today=None) -> dict:
    """
    Everything the settle job needs: results to grade, fixtures to void, and a
    reconciliation report.

    Corners are taken from football-data when available. ESPN's summary endpoint
    also carries them but costs one request per match, and no bettable market in
    scope needs corners — they are here only so a legacy corners bet remains
    gradeable rather than sitting pending forever.
    """
    espn = fetch_espn(days_back=days_back, today=today)
    archive = fetch_football_data()

    results = []
    for key, rec in espn["results"].items():
        ref = archive.get(key) or {}
        results.append(MatchResult(
            home=rec["home"], away=rec["away"],
            home_goals=rec["home_goals"], away_goals=rec["away_goals"],
            corners=ref.get("corners"),
        ))

    voids = [(v["home"], v["away"], v["reason"]) for v in espn["voids"].values()]

    return {
        "results": results,
        "voids": voids,
        "reconciliation": reconcile(espn["results"], archive) if archive else
                          {"confirmed": 0, "mismatches": [],
                           "awaiting_archive": [],
                           "note": "football-data unavailable; no cross-check performed"},
        "pending_fixtures": espn["pending"],
        "unknown_teams": espn["unknown_teams"],
        "requests_ok": espn["requests_ok"],
        "requests_failed": espn["requests_failed"],
    }
