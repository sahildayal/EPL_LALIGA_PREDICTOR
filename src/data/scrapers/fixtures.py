import requests
from datetime import datetime, timedelta
from src.data import cache

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# Full browser headers
ESPN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.espn.com/soccer/scoreboard/",
}


def get_world_cup_fixtures(days_ahead: int = 3) -> list:
    """
    Scrapes upcoming World Cup fixtures from ESPN.
    """
    cache_key = {"days": days_ahead}
    cached = cache.get("wc_fixtures", cache_key)
    if cached:
        return cached

    today = datetime.utcnow()
    events = []
    
    # Check "fifa.world" (World Cup) and "uefa.nations" as fallback
    leagues = ["fifa.world", "uefa.nations"]
    for league in leagues:
        for offset in range(days_ahead + 1):
            date_str = (today + timedelta(days=offset)).strftime("%Y%m%d")
            url = f"{ESPN_BASE}/{league}/scoreboard"
            try:
                resp = requests.get(url, params={"dates": date_str, "limit": 40}, headers=ESPN_HEADERS, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for event in data.get("events", []):
                        comps = event.get("competitions", [{}])
                        comp = comps[0] if comps else {}
                        competitors = comp.get("competitors", [])
                        if len(competitors) < 2:
                            continue

                        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

                        status_obj = event.get("status", {})
                        status = status_obj.get("type", {}).get("description", "Scheduled")
                        clock = status_obj.get("displayClock", "")

                        events.append({
                            "league": "World Cup" if league == "fifa.world" else "Nations League",
                            "name": event.get("name", ""),
                            "date": event.get("date", ""),
                            "home": home.get("team", {}).get("displayName", ""),
                            "away": away.get("team", {}).get("displayName", ""),
                            "home_score": home.get("score", ""),
                            "away_score": away.get("score", ""),
                            "status": status,
                            "clock": clock,
                            "venue": comp.get("venue", {}).get("fullName", ""),
                            "source": "espn",
                        })
            except Exception:
                pass

    # Sort & Deduplicate
    events.sort(key=lambda e: e.get("date", ""))
    seen = set()
    unique = []
    for e in events:
        key = (e["home"].lower(), e["away"].lower(), e.get("date", "")[:10])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    if unique:
        cache.set("wc_fixtures", cache_key, unique, ttl_seconds=900)  # 15-min cache
    return unique


def search_wc_fixture(team1: str, team2: str, days_ahead: int = 7) -> dict | None:
    all_fixtures = get_world_cup_fixtures(days_ahead=days_ahead)
    t1 = team1.lower()
    t2 = team2.lower()

    for f in all_fixtures:
        h = f["home"].lower()
        a = f["away"].lower()
        if (t1 in h or t1 in a) and (t2 in h or t2 in a):
            return f
    return None
