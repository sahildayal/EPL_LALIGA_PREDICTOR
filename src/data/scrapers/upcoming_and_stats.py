import requests
import json
import os
import logging
from datetime import datetime, timedelta, timezone
from src.data.scrapers.fixtures import ESPN_HEADERS, ESPN_BASE
from src.data.team_mapping import normalize_team_name

logger = logging.getLogger(__name__)

SCHEDULE_PATH = os.path.join("data", "processed", "daily_schedule.json")
PLAYER_STATS_PATH = os.path.join("data", "processed", "tournament_player_stats.json")

def scrape_upcoming_fixtures() -> list:
    """Scrapes uncompleted fixtures across EPL, La Liga, and UCL for today and next 2 days."""
    today = datetime.now(timezone.utc)
    fixtures = []
    dates = [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]
    
    leagues = ["eng.1", "esp.1", "uefa.champions"]
    for league in leagues:
        for date_str in dates:
            url = f"{ESPN_BASE}/{league}/scoreboard"
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
                            "league": "epl" if league == "eng.1" else ("laliga" if league == "esp.1" else "ucl"),
                            "home": normalize_team_name(home.get("team", {}).get("displayName", "")),
                            "away": normalize_team_name(away.get("team", {}).get("displayName", "")),
                            "date": ev.get("date", "")
                        })
            except Exception as e:
                logger.warning("Error scraping upcoming fixtures for %s: %s", league, e)
            
    os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
    with open(SCHEDULE_PATH, "w") as f:
        json.dump(fixtures, f, indent=2)
    return fixtures

def scrape_tournament_stats() -> dict:
    """Scrapes full club squad player rosters and statistics across EPL, La Liga, and UCL."""
    from src.data.cache import save_player_stats
    leagues = ["eng.1", "esp.1", "uefa.champions"]
    result = {"goals": {}, "assists": {}, "rosters": {}}
    
    for league in leagues:
        url = f"{ESPN_BASE}/{league}/teams"
        try:
            resp = requests.get(url, params={"limit": 50}, headers=ESPN_HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                sports = data.get("sports", [{}])
                leagues_data = sports[0].get("leagues", [{}]) if sports else []
                teams = leagues_data[0].get("teams", []) if leagues_data else []
                
                for t in teams:
                    team_obj = t.get("team", {})
                    team_id = team_obj.get("id")
                    team_name = normalize_team_name(team_obj.get("displayName", ""))
                    if not team_id:
                        continue
                        
                    roster_url = f"{ESPN_BASE}/{league}/teams/{team_id}/roster"
                    r_resp = requests.get(roster_url, headers=ESPN_HEADERS, timeout=8)
                    if r_resp.status_code == 200:
                        r_data = r_resp.json()
                        athletes = r_data.get("athletes", [])
                        team_roster = []
                        
                        for ath in athletes:
                            p_name = ath.get("displayName", "").lower().strip()
                            if not p_name:
                                continue
                            pos = ath.get("position", {}).get("abbreviation", "FW")
                            pos_cat = "DEF" if "D" in pos else ("CM" if "M" in pos or "M" in pos else "FW")
                            
                            stats_list = ath.get("statistics", [])
                            goals = 0.0
                            assists = 0.0
                            for s in stats_list:
                                s_name = s.get("name", "").lower()
                                val = float(s.get("value", 0.0) or 0.0)
                                if s_name == "goals":
                                    goals = val
                                elif s_name == "assists":
                                    assists = val
                                    
                            g90 = round(max(goals / 25.0, 0.05), 3) if pos_cat == "FW" else round(max(goals / 30.0, 0.02), 3)
                            a90 = round(max(assists / 25.0, 0.05), 3)
                            xg90 = round(g90 * 1.1, 3)
                            
                            team_roster.append({
                                "name": p_name,
                                "position": pos_cat,
                                "goals": goals,
                                "assists": assists,
                                "g90": g90,
                                "a90": a90
                            })
                            
                            result["goals"][p_name] = goals
                            result["assists"][p_name] = assists
                            save_player_stats(p_name, pos_cat, xg90, g90, a90, team_name, "")
                            
                        result["rosters"][team_name] = team_roster
        except Exception as e:
            logger.warning("Error scraping squad stats for %s: %s", league, e)
            
    os.makedirs(os.path.dirname(PLAYER_STATS_PATH), exist_ok=True)
    with open(PLAYER_STATS_PATH, "w") as f:
        json.dump(result, f, indent=2)
    return result
