import requests
import json
import os
from datetime import datetime, timedelta, timezone
from src.data.scrapers.fixtures import ESPN_HEADERS, ESPN_BASE
from src.data.team_mapping import normalize_team_name

SCHEDULE_PATH = os.path.join("data", "processed", "daily_schedule.json")
PLAYER_STATS_PATH = os.path.join("data", "processed", "tournament_player_stats.json")

def scrape_upcoming_fixtures() -> list:
    """Scrapes uncompleted fixtures for today and next 2 days from ESPN and saves them."""
    today = datetime.now(timezone.utc)
    fixtures = []
    dates = [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]
    
    for date_str in dates:
        url = f"{ESPN_BASE}/fifa.world/scoreboard"
        try:
            resp = requests.get(url, params={"dates": date_str}, headers=ESPN_HEADERS, timeout=8)
            if resp.status_code == 200:
                events = resp.json().get("events", [])
                for ev in events:
                    status_obj = ev.get("status", {})
                    completed = status_obj.get("type", {}).get("completed", False)
                    if completed:
                        continue
                    
                    comps = ev.get("competitions", [{}])
                    competitors = comps[0].get("competitors", []) if comps else []
                    if len(competitors) < 2:
                        continue
                    
                    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                    
                    fixtures.append({
                        "home": normalize_team_name(home.get("team", {}).get("displayName", "")),
                        "away": normalize_team_name(away.get("team", {}).get("displayName", "")),
                        "date": ev.get("date", "")
                    })
        except Exception:
            pass
            
    os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
    with open(SCHEDULE_PATH, "w") as f:
        json.dump(fixtures, f, indent=2)
    return fixtures

def scrape_tournament_stats() -> dict:
    """Scrapes World Cup tournament player statistics and saves them."""
    url = f"{ESPN_BASE}/fifa.world/statistics"
    result = {"goals": {}, "assists": {}}
    try:
        resp = requests.get(url, headers=ESPN_HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            for category in data.get("stats", []):
                cat_name = category.get("name")
                leaders = category.get("leaders", [])
                
                if cat_name == "goalsLeaders":
                    for l in leaders:
                        name = l.get("athlete", {}).get("displayName", "").lower().strip()
                        val = float(l.get("value", 0.0))
                        if name:
                            result["goals"][name] = val
                elif cat_name == "assistsLeaders":
                    for l in leaders:
                        name = l.get("athlete", {}).get("displayName", "").lower().strip()
                        val = float(l.get("value", 0.0))
                        if name:
                            result["assists"][name] = val
    except Exception:
        pass
        
    os.makedirs(os.path.dirname(PLAYER_STATS_PATH), exist_ok=True)
    with open(PLAYER_STATS_PATH, "w") as f:
        json.dump(result, f, indent=2)
    return result
