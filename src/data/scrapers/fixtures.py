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


def get_match_lineups(home_team: str, away_team: str, event_id: str = None) -> dict:
    """
    Gets lineups for the given match. If lineups aren't published,
    falls back to the lineups of each team's most recent completed game.
    """
    from src.data.team_mapping import normalize_team_name
    h_norm = normalize_team_name(home_team)
    a_norm = normalize_team_name(away_team)
    
    # Try to fetch lineups directly for this match event
    if event_id:
        lineups = _fetch_espn_event_lineup(event_id, h_norm, a_norm)
        if lineups:
            return lineups

    # Fallback: Find the event ID for the match, then fetch
    fixture = search_wc_fixture(home_team, away_team)
    if fixture:
        # Search ESPN schedule to find event id
        found_id = _find_espn_event_id(h_norm, a_norm)
        if found_id:
            lineups = _fetch_espn_event_lineup(found_id, h_norm, a_norm)
            if lineups:
                return lineups

    # Fallback Option A: Get lineups from each team's most recent completed match
    h_lineup = _fetch_team_recent_lineup(h_norm)
    a_lineup = _fetch_team_recent_lineup(a_norm)
    
    # Default backup list
    DEFAULT_PLAYERS = {
        "england": ["harry kane", "jude bellingham", "bukayo saka", "phil foden", "declan rice", "kieran trippier", "john stones", "kyle walker", "jordan pickford", "ollie watkins", "kobbie mainoo"],
        "france": ["kylian mbappe", "antoine griezmann", "olivier giroud", "dembele", "camavinga", "tchouameni", "theo hernandez", "upamecano", "saliba", "kounde", "maignan"],
        "argentina": ["lionel messi", "lautaro martinez", "julian alvarez", "enzo fernandez", "de paul", "mac allister", "otamendi", "romero", "lisandro martinez", "molina", "dibu martinez"],
        "portugal": ["cristiano ronaldo", "joao neves", "bruno fernandes", "bernardo silva", "rafael leao", "vitinha", "joao cancelo", "pepe", "ruben dias", "diogo dalot", "diogo costa"],
        "germany": ["jamal musiala", "florian wirtz", "kai havertz", "ilkay gundogan", "kroos", "andrich", "mittelstadt", "tah", "rudiger", "kimmich", "neuer"],
        "spain": ["alvaro morata", "lamine yamal", "nico williams", "pedri", "rodri", "ruiz", "cucurella", "laporte", "le normand", "carvajal", "simon"],
        "colombia": ["james rodriguez", "luis diaz", "jhon cordoba", "arias", "rios", "lerma", "mojica", "cuesta", "sanchez", "munoz", "vargas"],
        "canada": ["jonathan david", "alphonso davies", "larin", "shaffelburg", "eustaquio", "kone", "laryea", "miller", "bombito", "johnston", "crepeau"],
        "south africa": ["iqraam rayners", "themba zwane", "teboho mokoena", "aubrey modiba", "sphephelo sithole", "thapelo morena", "khuliso mudau", "mothobi mvala", "grant kekana", "ronwen williams", "relebohile mofokeng"]
    }

    if not h_lineup:
        h_lineup = DEFAULT_PLAYERS.get(h_norm, ["player1", "player2", "player3"])
    if not a_lineup:
        a_lineup = DEFAULT_PLAYERS.get(a_norm, ["player1", "player2", "player3"])

    return {
        "home_lineup": h_lineup,
        "away_lineup": a_lineup,
        "source": "fallback_recent_or_default"
    }

def _find_espn_event_id(team1_norm: str, team2_norm: str) -> str | None:
    from src.data.team_mapping import is_team_match
    # Query fifa.world scoreboard for active event IDs
    url = f"{ESPN_BASE}/fifa.world/scoreboard"
    try:
        resp = requests.get(url, headers=ESPN_HEADERS, timeout=8)
        if resp.status_code == 200:
            events = resp.json().get("events", [])
            for ev in events:
                title = ev.get("name", "").lower()
                if team1_norm in title or team2_norm in title:
                    # Double check match
                    comps = ev.get("competitions", [{}])
                    competitors = comps[0].get("competitors", []) if comps else []
                    names = [c.get("team", {}).get("displayName", "").lower() for c in competitors]
                    if any(is_team_match(team1_norm, n) for n in names) and any(is_team_match(team2_norm, n) for n in names):
                        return ev.get("id")
    except Exception:
        pass
    return None

def _fetch_espn_event_lineup(event_id: str, home_norm: str, away_norm: str) -> dict | None:
    from src.data.team_mapping import is_team_match
    url = f"{ESPN_BASE}/fifa.world/summary?event={event_id}"
    try:
        resp = requests.get(url, headers=ESPN_HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            rosters = data.get("rosters", [])
            if not rosters:
                return None
            
            h_players = []
            a_players = []
            
            for roster in rosters:
                team_name = roster.get("team", {}).get("displayName", "").lower()
                entries = roster.get("roster", [])
                is_home = is_team_match(home_norm, team_name)
                
                players = []
                for entry in entries:
                    # If lineup is announced, look for starting players
                    starter = entry.get("starter", False)
                    active = entry.get("active", False)
                    # Roster can list everyone, filter starters or active 11
                    if starter or active:
                        name = entry.get("athlete", {}).get("displayName", "")
                        if name:
                            players.append(name.lower().strip())
                
                # Take starters if present (len == 11), else all active
                starters_only = [p for p in entries if p.get("starter", False)]
                if len(starters_only) >= 11:
                    players = [p.get("athlete", {}).get("displayName", "").lower().strip() for p in starters_only]
                
                if is_home:
                    h_players = players[:11] if len(players) > 11 else players
                else:
                    a_players = players[:11] if len(players) > 11 else players
                    
            if h_players and a_players:
                return {
                    "home_lineup": h_players,
                    "away_lineup": a_players,
                    "source": "live_espn_announcement"
                }
    except Exception:
        pass
    return None

def _fetch_team_recent_lineup(team_norm: str) -> list:
    from src.data.team_mapping import is_team_match
    # Query team schedule to find recent completed matches
    for league in ["fifa.world", "uefa.nations", "uefa.euro"]:
        url = f"{ESPN_BASE}/{league}/scoreboard"
        try:
            # Get scoreboards for past few days
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                events = resp.json().get("events", [])
                for ev in events:
                    status = ev.get("status", {}).get("type", {}).get("name", "")
                    if status == "STATUS_FINAL":
                        comps = ev.get("competitions", [{}])
                        competitors = comps[0].get("competitors", []) if comps else []
                        names = [c.get("team", {}).get("displayName", "").lower() for c in competitors]
                        if any(is_team_match(team_norm, n) for n in names):
                            ev_id = ev.get("id")
                            lineups = _fetch_espn_event_lineup(ev_id, team_norm, "dummy")
                            if lineups and lineups.get("home_lineup"):
                                return lineups["home_lineup"]
        except Exception:
            pass
    return []
