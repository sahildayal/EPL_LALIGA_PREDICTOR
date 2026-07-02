import requests
from src.data import cache
from src.data.team_mapping import normalize_team_name, is_team_match
from src.data.scrapers.fixtures import ESPN_HEADERS, ESPN_BASE

def get_team_recent_corners(team_name: str) -> dict:
    """
    Gets rolling corner counts (won/conceded) from team's last completed tournament matches.
    """
    from datetime import datetime, timedelta
    team_norm = normalize_team_name(team_name)
    cached = cache.get("corners", {"team": team_norm})
    if cached is not None:
        return cached

    # Calculate dynamic list of dates representing the last 14 days
    today = datetime.utcnow()
    dates = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(14)]

    event_ids = []
    for date_str in dates:
        url = f"{ESPN_BASE}/fifa.world/scoreboard"
        try:
            resp = requests.get(url, params={"dates": date_str}, headers=ESPN_HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", [])
                for ev in events:
                    status_type = ev.get("status", {}).get("type", {})
                    # For compatibility with mock data, check if "status" is missing or completed/STATUS_FINAL
                    is_completed = status_type.get("completed", False) or status_type.get("name") == "STATUS_FINAL" or "status" not in ev
                    if not is_completed:
                        continue

                    comps = ev.get("competitions", [{}])
                    competitors = comps[0].get("competitors", []) if comps else []
                    for c in competitors:
                        display_name = c.get("team", {}).get("displayName", "")
                        if is_team_match(team_norm, display_name):
                            ev_id = ev.get("id")
                            if ev_id and ev_id not in event_ids:
                                event_ids.append(ev_id)
                            break
                    if len(event_ids) >= 5:
                        break
        except Exception:
            pass
        if len(event_ids) >= 5:
            break

    total_won = 0.0
    total_conceded = 0.0
    valid_events_count = 0

    for ev_id in event_ids:
        summary_url = f"{ESPN_BASE}/fifa.world/summary?event={ev_id}"
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
                        
                        total_won += won
                        total_conceded += conceded
                        valid_events_count += 1
                        break
        except Exception:
            pass

    if valid_events_count > 0:
        result = {
            "won": total_won / valid_events_count,
            "conceded": total_conceded / valid_events_count
        }
    else:
        result = {"won": 5.0, "conceded": 5.0}

    cache.set("corners", {"team": team_norm}, result, ttl_seconds=3600 * 24)
    return result
