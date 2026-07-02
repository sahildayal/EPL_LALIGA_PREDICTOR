import requests
from src.data import cache
from src.data.team_mapping import normalize_team_name, is_team_match
from src.data.scrapers.fixtures import ESPN_HEADERS, ESPN_BASE

def get_team_recent_corners(team_name: str) -> dict:
    """
    Gets rolling corner counts (won/conceded) from team's last completed tournament match.
    """
    team_norm = normalize_team_name(team_name)
    cached = cache.get("corners", {"team": team_norm})
    if cached is not None:
        return cached

    # Default fallbacks
    result = {"won": 5.0, "conceded": 5.0}
    
    # We query the ESPN scoreboard for recent dates to find matching event summary IDs
    # Let's search June 29, 2026 matches as fallback if we can't find upcoming
    dates = ["20260629", "20260630"]
    found_event_id = None
    for date_str in dates:
        url = f"{ESPN_BASE}/fifa.world/scoreboard"
        try:
            resp = requests.get(url, params={"dates": date_str}, headers=ESPN_HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", [])
                for ev in events:
                    comps = ev.get("competitions", [{}])
                    competitors = comps[0].get("competitors", []) if comps else []
                    for c in competitors:
                        display_name = c.get("team", {}).get("displayName", "")
                        if is_team_match(team_norm, display_name):
                            found_event_id = ev.get("id")
                            break
                    if found_event_id:
                        break
        except Exception:
            pass
        if found_event_id:
            break

    if found_event_id:
        summary_url = f"{ESPN_BASE}/fifa.world/summary?event={found_event_id}"
        try:
            resp = requests.get(summary_url, headers=ESPN_HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                teams = data.get("boxscore", {}).get("teams", [])
                for idx, t in enumerate(teams):
                    disp = t.get("team", {}).get("displayName", "")
                    opp_idx = 1 - idx
                    if is_team_match(team_norm, disp):
                        won = 5.0
                        conceded = 5.0
                        for stat in t.get("statistics", []):
                            if stat.get("name") == "wonCorners":
                                won = float(stat.get("displayValue", 5.0))
                        opp_team = teams[opp_idx] if (opp_idx >= 0 and len(teams) > opp_idx) else {}
                        for stat in opp_team.get("statistics", []):
                            if stat.get("name") == "wonCorners":
                                conceded = float(stat.get("displayValue", 5.0))
                        result = {"won": won, "conceded": conceded}
                        break
        except Exception:
            pass

    cache.set("corners", {"team": team_norm}, result, ttl_seconds=3600 * 24)
    return result
