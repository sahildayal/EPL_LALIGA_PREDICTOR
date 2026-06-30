import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone
from src.data import cache

NEGATIVE_KEYWORDS = [
    "injury", "injured", "doubtful", "doubt", "suspended", "suspension",
    "crisis", "illness", "ill", "ruled out", "withdraw", "unfit", "concern",
    "hamstring", "knee", "ankle", "muscle", "torn", "fracture", "surgery"
]
POSITIVE_KEYWORDS = [
    "returns", "return", "fit", "recovered", "back in", "cleared",
    "available", "training", "sharp form", "confidence", "motivation"
]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _score_headline(text: str) -> float:
    text_lower = text.lower()
    score = 0.0
    for kw in NEGATIVE_KEYWORDS:
        if kw in text_lower:
            score -= 0.1
    for kw in POSITIVE_KEYWORDS:
        if kw in text_lower:
            score += 0.05
    return max(-0.5, min(0.3, score))


def get_sentiment(entity: str) -> dict:
    """Fetch news for an entity and return sentiment score."""
    cached = cache.get("news", {"entity": entity})
    if cached:
        return cached

    query = entity.replace(" ", "+") + "+soccer"
    url = GOOGLE_NEWS_RSS.format(query=query)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return {"score": 0.0, "flags": []}
        
        root = ET.fromstring(resp.content)
        score = 0.0
        flags = []
        
        # Parse top 15 news articles
        count = 0
        for item in root.iter("item"):
            title_el = item.find("title")
            title = title_el.text if title_el is not None else ""
            if title:
                s = _score_headline(title)
                score += s
                if s < -0.05:
                    flags.append(title[:80])
                count += 1
            if count >= 15:
                break
                
        result = {
            "score": round(max(-0.5, min(0.3, score)), 3),
            "flags": flags[:5],
        }
        cache.set("news", {"entity": entity}, result, ttl_seconds=3600 * 2)  # cache 2 hours
        return result
    except Exception:
        return {"score": 0.0, "flags": []}


def get_roster_health(team: str, roster: list) -> float:
    """
    Queries news headlines involving the team and parses for player injury keywords.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        url = f"https://news.google.com/rss/search?q={team.replace(' ', '+')}+football+injury"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return 1.0
        soup = BeautifulSoup(resp.text, "xml")
        titles = [item.title.text.lower() for item in soup.find_all("item")]
    except Exception:
        titles = []
        
    injury_words = ["injury", "injured", "out", "suspended", "doubtful", "miss", "absent", "hamstring", "knee"]
    flagged = 0
    for player in roster:
        p_name = player.lower().strip()
        for title in titles:
            if p_name in title and any(w in title for w in injury_words):
                flagged += 1
                break
                
    health = 1.0 - (flagged / 11)
    return max(0.5, health)

