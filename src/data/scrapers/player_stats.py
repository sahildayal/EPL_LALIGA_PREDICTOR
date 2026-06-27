import requests
import re
from bs4 import BeautifulSoup
from src.data import cache
from src.data.scrapers.elo_db import get_national_elo
from src.data.cache import save_player_stats, get_player_stats_cache

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Seeds containing player club form and national team coefficients
PLAYER_SEEDS = {
    "erling haaland": {
        "club_team": "manchester city", "intl_team": "norway",
        "xg_per_90_club": 0.93, "xg_per_90_intl": 0.85,
        "goals_per_90_club": 0.94, "goals_per_90_intl": 0.88,
        "assists_per_90": 0.15, "position": "CF",
    },
    "kylian mbappe": {
        "club_team": "real madrid", "intl_team": "france",
        "xg_per_90_club": 0.75, "xg_per_90_intl": 0.80,
        "goals_per_90_club": 0.72, "goals_per_90_intl": 0.82,
        "assists_per_90": 0.32, "position": "FW",
    },
    "harry kane": {
        "club_team": "bayern munich", "intl_team": "england",
        "xg_per_90_club": 0.82, "xg_per_90_intl": 0.78,
        "goals_per_90_club": 0.78, "goals_per_90_intl": 0.75,
        "assists_per_90": 0.28, "position": "CF",
    },
    "lionel messi": {
        "club_team": "inter miami", "intl_team": "argentina",
        "xg_per_90_club": 0.58, "xg_per_90_intl": 0.65,
        "goals_per_90_club": 0.62, "goals_per_90_intl": 0.68,
        "assists_per_90": 0.50, "position": "RW",
    },
    "cristiano ronaldo": {
        "club_team": "al nassr", "intl_team": "portugal",
        "xg_per_90_club": 0.68, "xg_per_90_intl": 0.60,
        "goals_per_90_club": 0.70, "goals_per_90_intl": 0.64,
        "assists_per_90": 0.15, "position": "FW",
    },
    "vinicius jr": {
        "club_team": "real madrid", "intl_team": "brazil",
        "xg_per_90_club": 0.52, "xg_per_90_intl": 0.45,
        "goals_per_90_club": 0.55, "goals_per_90_intl": 0.48,
        "assists_per_90": 0.38, "position": "LW",
    },
    "jude bellingham": {
        "club_team": "real madrid", "intl_team": "england",
        "xg_per_90_club": 0.38, "xg_per_90_intl": 0.42,
        "goals_per_90_club": 0.35, "goals_per_90_intl": 0.38,
        "assists_per_90": 0.30, "position": "CM",
    },
    "bukayo saka": {
        "club_team": "arsenal", "intl_team": "england",
        "xg_per_90_club": 0.38, "xg_per_90_intl": 0.35,
        "goals_per_90_club": 0.40, "goals_per_90_intl": 0.38,
        "assists_per_90": 0.35, "position": "RW",
    },
    "phil foden": {
        "club_team": "manchester city", "intl_team": "england",
        "xg_per_90_club": 0.35, "xg_per_90_intl": 0.30,
        "goals_per_90_club": 0.38, "goals_per_90_intl": 0.32,
        "assists_per_90": 0.32, "position": "LW",
    },
    "lautaro martinez": {
        "club_team": "inter milan", "intl_team": "argentina",
        "xg_per_90_club": 0.65, "xg_per_90_intl": 0.58,
        "goals_per_90_club": 0.60, "goals_per_90_intl": 0.54,
        "assists_per_90": 0.18, "position": "CF",
    },
    "antoine griezmann": {
        "club_team": "atletico madrid", "intl_team": "france",
        "xg_per_90_club": 0.35, "xg_per_90_intl": 0.42,
        "goals_per_90_club": 0.38, "goals_per_90_intl": 0.40,
        "assists_per_90": 0.45, "position": "AM",
    },
    "robert lewandowski": {
        "club_team": "barcelona", "intl_team": "poland",
        "xg_per_90_club": 0.72, "xg_per_90_intl": 0.62,
        "goals_per_90_club": 0.68, "goals_per_90_intl": 0.58,
        "assists_per_90": 0.20, "position": "CF",
    },
    "alvaro morata": {
        "club_team": "ac milan", "intl_team": "spain",
        "xg_per_90_club": 0.48, "xg_per_90_intl": 0.52,
        "goals_per_90_club": 0.45, "goals_per_90_intl": 0.50,
        "assists_per_90": 0.15, "position": "CF",
    },
    "jamal musiala": {
        "club_team": "bayern munich", "intl_team": "germany",
        "xg_per_90_club": 0.32, "xg_per_90_intl": 0.38,
        "goals_per_90_club": 0.30, "goals_per_90_intl": 0.35,
        "assists_per_90": 0.28, "position": "AM",
    },
    "florian wirtz": {
        "club_team": "bayer leverkusen", "intl_team": "germany",
        "xg_per_90_club": 0.30, "xg_per_90_intl": 0.35,
        "goals_per_90_club": 0.28, "goals_per_90_intl": 0.32,
        "assists_per_90": 0.40, "position": "AM",
    },
}

POSITION_DEFAULTS = {
    "CF": {"xg": 0.42, "goals": 0.38, "assists": 0.12},
    "FW": {"xg": 0.32, "goals": 0.28, "assists": 0.20},
    "LW": {"xg": 0.28, "goals": 0.25, "assists": 0.25},
    "RW": {"xg": 0.28, "goals": 0.25, "assists": 0.25},
    "AM": {"xg": 0.22, "goals": 0.18, "assists": 0.32},
    "CM": {"xg": 0.12, "goals": 0.10, "assists": 0.22},
    "DEF": {"xg": 0.04, "goals": 0.03, "assists": 0.06},
}


def get_player_stats(name: str) -> dict:
    """
    Get composite player stats. Blends 60% national team stats + 40% club stats.
    Caches values in SQLite player_statistics table.
    """
    key = name.lower().strip()
    
    # 1. Check local SQLite cache first
    cached = get_player_stats_cache(key)
    if cached:
        return cached

    # 2. Check static seeds
    for seed_name, data in PLAYER_SEEDS.items():
        if seed_name == key or seed_name in key or key in seed_name:
            xg_blend = 0.60 * data["xg_per_90_intl"] + 0.40 * data["xg_per_90_club"]
            goals_blend = 0.60 * data["goals_per_90_intl"] + 0.40 * data["goals_per_90_club"]
            
            result = {
                "name": key,
                "position": data["position"],
                "xg_per_90": round(xg_blend, 3),
                "goals_per_90": round(goals_blend, 3),
                "assists_per_90": data["assists_per_90"],
                "source": "seeded_blend"
            }
            save_player_stats(key, result["position"], result["xg_per_90"], result["goals_per_90"], result["assists_per_90"], data.get("club_team"), data.get("intl_team"))
            return result

    # 3. Dynamic FBRef Scraper
    scraped = _scrape_fbref_player(name)
    if scraped:
        pos = scraped.get("position", "FW")
        defaults = POSITION_DEFAULTS.get(pos, POSITION_DEFAULTS["FW"])
        
        # Blend: 60% default intl profile, 40% club scraped
        xg_blend = 0.60 * defaults["xg"] + 0.40 * scraped["xg_per_90"]
        goals_blend = 0.60 * defaults["goals"] + 0.40 * scraped["goals_per_90"]
        assists_blend = 0.60 * defaults["assists"] + 0.40 * scraped["assists_per_90"]
        
        result = {
            "name": key,
            "position": pos,
            "xg_per_90": round(xg_blend, 3),
            "goals_per_90": round(goals_blend, 3),
            "assists_per_90": round(assists_blend, 3),
            "source": "scraped_blend"
        }
        save_player_stats(key, pos, result["xg_per_90"], result["goals_per_90"], result["assists_per_90"], "", "")
        return result

    # 4. Standard position default fallback
    result = {
        "name": key,
        "position": "FW",
        "xg_per_90": POSITION_DEFAULTS["FW"]["xg"],
        "goals_per_90": POSITION_DEFAULTS["FW"]["goals"],
        "assists_per_90": POSITION_DEFAULTS["FW"]["assists"],
        "source": "position_default"
    }
    save_player_stats(key, "FW", result["xg_per_90"], result["goals_per_90"], result["assists_per_90"], "", "")
    return result


def _scrape_fbref_player(name: str) -> dict:
    try:
        search_url = f"https://fbref.com/search/search.fcgi?search={name.replace(' ', '+')}"
        resp = requests.get(search_url, headers=HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            if "/players/" in resp.url:
                return _parse_player_page(soup)
            
            result = soup.find("div", {"id": "searches"})
            if result:
                link = result.find("a", href=re.compile(r"/players/"))
                if link:
                    player_url = "https://fbref.com" + link["href"]
                    r2 = requests.get(player_url, headers=HEADERS, timeout=8)
                    if r2.status_code == 200:
                        return _parse_player_page(BeautifulSoup(r2.text, "lxml"))
    except Exception:
        pass
    return {}


def _parse_player_page(soup: BeautifulSoup) -> dict:
    try:
        std_table = soup.find("table", {"id": re.compile(r"stats_standard")})
        xg_per_90 = goals_per_90 = assists_per_90 = None
        position = "FW"

        if std_table:
            rows = std_table.find("tbody").find_all("tr")
            for row in reversed(rows):
                if row.get("class") and "partial_table" in row.get("class", []):
                    continue
                xg_cell = row.find("td", {"data-stat": "xg_per90"})
                goals_cell = row.find("td", {"data-stat": "goals_per90"})
                assists_cell = row.find("td", {"data-stat": "assists_per90"})
                if xg_cell and xg_cell.text.strip():
                    try:
                        xg_per_90 = float(xg_cell.text)
                        goals_per_90 = float(goals_cell.text) if goals_cell else 0.25
                        assists_per_90 = float(assists_cell.text) if assists_cell else 0.15
                    except ValueError:
                        pass
                    break

        pos_span = soup.find("strong", string=re.compile("Position"))
        if pos_span and pos_span.next_sibling:
            pos_text = str(pos_span.next_sibling)
            if "DF" in pos_text:
                position = "DEF"
            elif "MF" in pos_text:
                position = "CM"
            elif "FW" in pos_text:
                position = "FW"

        return {
            "xg_per_90": xg_per_90 or 0.3,
            "goals_per_90": goals_per_90 or 0.25,
            "assists_per_90": assists_per_90 or 0.15,
            "position": position,
        }
    except Exception:
        return {}
