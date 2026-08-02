"""
Live club Elo ratings from ClubElo (http://api.clubelo.com).

Replaces the hardcoded CLUB_ELO guesses in elo_db.py, which were badly stale
(e.g. Arsenal listed at 1910 against a real rating of 2063.8 on 2026-08-01).

Scale note: ClubElo club ratings and eloratings.net national-team ratings are
DIFFERENT scales and must never be compared or blended. Club ratings live here;
national ratings stay in elo_db.NATIONAL_TEAM_ELO.
"""
import csv
import io
from datetime import date

import requests

from src.data import cache
from src.data.canonical_teams import canonical, UnknownTeam

API_URL = "http://api.clubelo.com/{date}"
CACHE_TTL_SECONDS = 3600 * 24

# ClubElo uses its own short names. Anything not listed here passes through
# lowercased, which already matches for Arsenal, Chelsea, Liverpool, Barcelona,
# Real Madrid, Villarreal, Sevilla, Girona, Osasuna, Mallorca and most others.
CLUBELO_ALIASES = {
    "man city": "manchester city",
    "man united": "manchester united",
    "forest": "nottingham forest",
    "wolves": "wolverhampton",
    "atletico": "atletico madrid",
    "betis": "real betis",
    "celta": "celta vigo",
    "bilbao": "athletic bilbao",
    "sociedad": "real sociedad",
    "valladolid": "real valladolid",
    "paris sg": "paris saint-germain",
    "inter": "inter milan",
    "bayern": "bayern munich",
    "dortmund": "borussia dortmund",
    "leipzig": "rb leipzig",
    "leverkusen": "bayer leverkusen",
    "sporting": "sporting cp",
}

# ClubElo country code -> our league key
COUNTRY_TO_LEAGUE = {"ENG": "epl", "ESP": "laliga"}


class ClubEloUnavailable(RuntimeError):
    """Raised when ratings cannot be fetched. Never substitute fabricated values."""


def _canonical(clubelo_name: str) -> str:
    """
    Resolves a ClubElo name via the shared registry. ClubElo covers every league
    in Europe, so plenty of names are legitimately outside our EPL/La Liga
    registry; those are returned as a slug and simply never looked up.
    """
    try:
        return canonical(clubelo_name)
    except UnknownTeam:
        return clubelo_name.strip().lower()


def fetch_snapshot(on_date: str = None) -> dict:
    """
    Returns {canonical_team_name: {"elo": float, "country": str, "level": int}}
    for every club ClubElo tracks on the given date (default: today).

    Raises ClubEloUnavailable rather than returning partial or invented data.
    """
    on_date = on_date or date.today().isoformat()

    cached = cache.get("clubelo_snapshot", {"date": on_date})
    if cached:
        return cached

    try:
        resp = requests.get(API_URL.format(date=on_date), timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        raise ClubEloUnavailable(f"ClubElo fetch failed for {on_date}: {exc}") from exc

    ratings = {}
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        club = (row.get("Club") or "").strip()
        raw_elo = (row.get("Elo") or "").strip()
        if not club or club == "None" or not raw_elo:
            continue
        try:
            elo = float(raw_elo)
        except ValueError:
            continue
        try:
            level = int(row.get("Level") or 0)
        except ValueError:
            level = 0
        ratings[_canonical(club)] = {
            "elo": round(elo, 2),
            "country": (row.get("Country") or "").strip(),
            "level": level,
        }

    if not ratings:
        raise ClubEloUnavailable(f"ClubElo returned no usable rows for {on_date}")

    cache.set("clubelo_snapshot", {"date": on_date}, ratings, ttl_seconds=CACHE_TTL_SECONDS)
    return ratings


def get_league_ratings(league: str, on_date: str = None) -> dict:
    """
    Returns {team: elo} for clubs ClubElo currently flags as the top division of
    one league.

    WARNING: ClubElo's Level field lags the promotion/relegation boundary. On
    2026-08-01 it still listed Girona, Mallorca and Oviedo as Spanish level 1
    while the actual 2026/27 La Liga fixture list contains Racing Santander,
    Deportivo and Malaga (level 2 in the same snapshot). Do not use this to
    decide who is in the league.

    Use get_ratings_for() with the real fixture list instead. This function is
    kept only for exploratory work.
    """
    country = {v: k for k, v in COUNTRY_TO_LEAGUE.items()}.get(league)
    if not country:
        raise ValueError(f"Unknown league {league!r}; expected one of {sorted(COUNTRY_TO_LEAGUE.values())}")
    snap = fetch_snapshot(on_date)
    return {
        team: meta["elo"]
        for team, meta in snap.items()
        if meta["country"] == country and meta["level"] == 1
    }


def get_ratings_for(teams, on_date: str = None) -> tuple:
    """
    Returns ({team: elo}, [missing]) for an explicit list of canonical names.

    This is the correct entry point: league membership comes from the fixture
    list, not from ClubElo's stale Level flag, so newly promoted clubs are rated
    normally instead of silently dropping out. Missing names are returned rather
    than defaulted, so a caller can decide loudly what to do.
    """
    snap = fetch_snapshot(on_date)
    ratings, missing = {}, []
    for t in teams:
        key = canonical(t, strict=False)
        if key in snap:
            ratings[key] = snap[key]["elo"]
        else:
            missing.append(t)
    return ratings, missing


def get_club_ratings(on_date: str = None) -> dict:
    """Flat {team: elo} across every club ClubElo tracks."""
    return {team: meta["elo"] for team, meta in fetch_snapshot(on_date).items()}
