import requests
import json
import re
from bs4 import BeautifulSoup
from src.data import cache
from src.data.scrapers.elo_db import get_national_elo
from src.data.team_mapping import normalize_team_name

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# National team scoring priors for 2026 World Cup participants
INTL_SCORING_PRIORS = {
    "argentina":   {"avg_goals": 2.1, "avg_conceded": 0.6},
    "france":      {"avg_goals": 2.2, "avg_conceded": 0.9},
    "brazil":      {"avg_goals": 2.0, "avg_conceded": 0.7},
    "england":     {"avg_goals": 1.8, "avg_conceded": 0.8},
    "spain":       {"avg_goals": 1.9, "avg_conceded": 0.7},
    "portugal":    {"avg_goals": 2.1, "avg_conceded": 0.8},
    "netherlands": {"avg_goals": 1.9, "avg_conceded": 1.0},
    "germany":     {"avg_goals": 1.7, "avg_conceded": 1.1},
    "italy":       {"avg_goals": 1.5, "avg_conceded": 0.8},
    "croatia":     {"avg_goals": 1.6, "avg_conceded": 0.9},
    "belgium":     {"avg_goals": 1.8, "avg_conceded": 0.9},
    "morocco":     {"avg_goals": 1.4, "avg_conceded": 0.7},
    "denmark":     {"avg_goals": 1.7, "avg_conceded": 0.9},
    "switzerland": {"avg_goals": 1.7, "avg_conceded": 0.9},
    "uruguay":     {"avg_goals": 1.6, "avg_conceded": 0.8},
    "colombia":    {"avg_goals": 1.6, "avg_conceded": 0.9},
    "mexico":      {"avg_goals": 1.5, "avg_conceded": 1.0},
    "usa":         {"avg_goals": 1.5, "avg_conceded": 1.0},
    "japan":       {"avg_goals": 1.7, "avg_conceded": 0.9},
    "south korea": {"avg_goals": 1.5, "avg_conceded": 1.0},
    "senegal":     {"avg_goals": 1.4, "avg_conceded": 0.8},
    "australia":   {"avg_goals": 1.3, "avg_conceded": 1.0},
    "canada":      {"avg_goals": 1.4, "avg_conceded": 1.1},
    "ecuador":     {"avg_goals": 1.3, "avg_conceded": 0.9},
    "chile":       {"avg_goals": 1.3, "avg_conceded": 1.0},
    "saudi arabia": {"avg_goals": 1.2, "avg_conceded": 1.1},
    "iran":        {"avg_goals": 1.4, "avg_conceded": 0.9},
}

ESPN_LEAGUES = [
    "fifa.world", "uefa.nations", "uefa.euro", "fifa.worldq.uefa",
    "fifa.worldq.conmebol", "fifa.worldq.concacaf", "eng.1", "esp.1", "ger.1"
]


def get_team_data(team_name: str) -> dict:
    """
    Retrieves team form, ELO, and scoring averages.
    """
    name_lower = normalize_team_name(team_name)
    cached = cache.get("fbref_team", {"team": name_lower})
    if cached:
        return cached

    # Try Understat (in case it is a club for mapping player details)
    understat_data = get_understat_team(team_name)
    if understat_data:
        understat_data["elo"] = get_national_elo(team_name)
        understat_data["data_sources"] = ["Understat (live xG)"]
        cache.set("fbref_team", {"team": name_lower}, understat_data, ttl_seconds=3600 * 6)
        return understat_data

    # Try ESPN for international team form
    priors = INTL_SCORING_PRIORS.get(name_lower, {"avg_goals": 1.4, "avg_conceded": 1.1})
    elo = get_national_elo(team_name)

    result = {
        "team": team_name,
        "elo": elo,
        "avg_goals": priors["avg_goals"],
        "avg_conceded": priors["avg_conceded"],
        "form": 0.60,
        "is_national": True,
        "data_sources": ["FIFA/EloRatings", "Historical priors"],
    }

    # Fetch form
    espn_form = _get_espn_intl_form(team_name)
    if espn_form:
        result.update(espn_form)

    cache.set("fbref_team", {"team": name_lower}, result, ttl_seconds=3600 * 6)
    return result


ESPN_TEAMS_CACHE = {}

def _get_espn_intl_form(team_name: str) -> dict:
    name_lower = team_name.lower()
    for league in ESPN_LEAGUES:
        try:
            if league not in ESPN_TEAMS_CACHE:
                url = f"{ESPN_BASE}/{league}/teams"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    ESPN_TEAMS_CACHE[league] = resp.json()
                else:
                    ESPN_TEAMS_CACHE[league] = {}

            data = ESPN_TEAMS_CACHE[league]
            sports = data.get("sports", [{}])
            leagues_data = sports[0].get("leagues", [{}]) if sports else [{}]
            teams = leagues_data[0].get("teams", []) if leagues_data else []

            for team_entry in teams:
                t = team_entry.get("team", {})
                display = t.get("displayName", "").lower()
                if name_lower in display or display in name_lower:
                    team_id = t.get("id")
                    form = _get_espn_team_form(league, team_id)
                    return {"form": form, "data_sources": [f"ESPN ({league})"]}
        except Exception:
            continue
    return {}


def _get_espn_team_form(league: str, team_id: str) -> float:
    try:
        url = f"{ESPN_BASE}/{league}/teams/{team_id}/schedule"
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return 0.5

        events = resp.json().get("events", [])
        results = []
        for ev in reversed(events):
            comps = ev.get("competitions", [{}])
            comp = comps[0] if comps else {}
            competitors = comp.get("competitors", [])
            for c in competitors:
                if str(c.get("id")) == str(team_id):
                    outcome = c.get("winner")
                    if outcome is True:
                        results.append("w")
                    elif outcome is False:
                        results.append("l")
                    else:
                        results.append("d")
            if len(results) >= 8:
                break

        if not results:
            return 0.5
        wins = results.count("w")
        draws = results.count("d")
        return round((wins + 0.5 * draws) / len(results), 3)
    except Exception:
        return 0.5


def get_understat_team(team_name: str) -> dict:
    # Basic understat matching for clubs if needed for player context
    return {}


def get_h2h(team1: str, team2: str) -> dict:
    cached = cache.get("h2h_football", {"t1": team1.lower(), "t2": team2.lower()})
    if cached:
        return cached

    H2H_SEEDS = {
        frozenset(["portugal", "spain"]):       {"home_wins": 10, "draws": 7,  "away_wins": 14, "total": 31},
        frozenset(["england", "france"]):        {"home_wins": 17, "draws": 7,  "away_wins": 9,  "total": 33},
        frozenset(["brazil", "argentina"]):      {"home_wins": 36, "draws": 25, "away_wins": 42, "total": 103},
        frozenset(["germany", "france"]):        {"home_wins": 20, "draws": 11, "away_wins": 20, "total": 51},
        frozenset(["spain", "germany"]):         {"home_wins": 11, "draws": 6,  "away_wins": 9,  "total": 26},
        frozenset(["england", "germany"]):       {"home_wins": 13, "draws": 5,  "away_wins": 9,  "total": 27},
    }

    key = frozenset([team1.lower(), team2.lower()])
    if key in H2H_SEEDS:
        data = dict(H2H_SEEDS[key])
        t1_is_first = team1.lower() < team2.lower()
        h2h = {
            "team1_wins": data["home_wins"] if t1_is_first else data["away_wins"],
            "draws": data["draws"],
            "team2_wins": data["away_wins"] if t1_is_first else data["home_wins"],
            "total": data["total"],
        }
        h2h["team1_win_rate"] = round(h2h["team1_wins"] / h2h["total"], 4)
        cache.set("h2h_football", {"t1": team1.lower(), "t2": team2.lower()}, h2h, ttl_seconds=86400)
        return h2h

    return {"team1_wins": 3, "draws": 3, "team2_wins": 3, "total": 9, "team1_win_rate": 0.33}
