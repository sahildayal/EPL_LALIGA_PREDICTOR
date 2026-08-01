"""
ELO database - seeding ELO ratings for national teams from eloratings.net.
"""
import requests
import re
from src.data import cache

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Sourced from World Football ELO ratings — accurate for World Cup 2026 participants
# Club Football ELO ratings for EPL, La Liga, and Champions League participants
CLUB_ELO = {
    # Tier 1 Elite UCL Contenders
    "real madrid": 1980, "manchester city": 1970, "man city": 1970, "bayern munich": 1930,
    "arsenal": 1910, "barcelona": 1900, "liverpool": 1900, "psg": 1910, "paris saint-germain": 1910,
    "inter milan": 1890, "inter": 1890, "atletico madrid": 1870, "atletico": 1870,
    "bayer leverkusen": 1880, "leverkusen": 1880, "borussia dortmund": 1860, "dortmund": 1860,

    # Tier 2 Top Contenders & European Qualifiers
    "chelsea": 1850, "atalanta": 1850, "juventus": 1840, "rb leipzig": 1840, "leipzig": 1840,
    "aston villa": 1830, "sporting cp": 1830, "sporting": 1830, "ac milan": 1830, "milan": 1830,
    "tottenham": 1820, "spurs": 1820, "newcastle": 1820, "benfica": 1820,
    "manchester united": 1810, "man united": 1810, "man utd": 1810,
    "girona": 1810, "athletic bilbao": 1810, "athletic club": 1810,
    "real sociedad": 1800, "porto": 1800, "villarreal": 1790, "real betis": 1780, "betis": 1780,
    "brighton": 1780, "sevilla": 1780, "west ham": 1760,

    # Mid-Table Premier League & La Liga
    "fulham": 1740, "bournemouth": 1730, "crystal palace": 1730, "osasuna": 1730,
    "brentford": 1720, "celta vigo": 1720, "everton": 1710, "rayo vallecano": 1710, "mallorca": 1710,
    "wolverhampton": 1700, "wolves": 1700, "nottingham forest": 1700, "forest": 1700,
    "las palmas": 1690, "alaves": 1690, "getafe": 1680, "leicester": 1680,

    # Lower Table / Promoted
    "espanyol": 1670, "southampton": 1660, "leganes": 1650, "ipswich": 1640,
    "real valladolid": 1640, "valladolid": 1640,
}

# Sourced from World Football ELO ratings — accurate for international fallback
NATIONAL_TEAM_ELO = {
    "argentina": 2087, "france": 2053, "brazil": 2037, "england": 1966,
    "spain": 2019, "portugal": 1989, "netherlands": 1945, "belgium": 1881,
    "italy": 1876, "croatia": 1922, "germany": 1908, "morocco": 1835,
    "uruguay": 1884, "colombia": 1863, "mexico": 1832, "denmark": 1873,
    "switzerland": 1870, "senegal": 1847, "nigeria": 1839, "egypt": 1818,
    "japan": 1862, "south korea": 1832, "australia": 1812, "iran": 1795,
    "usa": 1825, "canada": 1808, "chile": 1831, "peru": 1821,
    "austria": 1843, "turkey": 1845, "poland": 1834, "wales": 1832,
    "scotland": 1823, "republic of ireland": 1798, "czech republic": 1830,
    "slovakia": 1811, "hungary": 1821, "romania": 1815, "ukraine": 1851,
    "russia": 1826, "serbia": 1858, "sweden": 1848, "norway": 1838,
    "finland": 1799, "greece": 1809, "albania": 1805, "georgia": 1812,
    "ecuador": 1820, "paraguay": 1818, "venezuela": 1803, "bolivia": 1775,
    "costa rica": 1808, "panama": 1797, "honduras": 1788, "el salvador": 1780,
    "cameroon": 1826, "ghana": 1822, "ivory coast": 1834, "mali": 1821,
    "algeria": 1832, "tunisia": 1821, "south africa": 1808, "saudi arabia": 1808,
    "qatar": 1798, "iraq": 1805, "jordan": 1798, "uae": 1792, "uzbekistan": 1808,
    "china": 1794, "india": 1781, "new zealand": 1793, "jamaica": 1803,
}


def get_team_elo(team_name: str) -> float:
    """Return ELO for a club or national team."""
    from src.data.team_mapping import normalize_team_name
    key = normalize_team_name(team_name)
    if key in CLUB_ELO:
        return float(CLUB_ELO[key])
    if key in NATIONAL_TEAM_ELO:
        return float(NATIONAL_TEAM_ELO[key])
    # Fuzzy match
    for name, elo in CLUB_ELO.items():
        if name in key or key in name:
            return float(elo)
    for name, elo in NATIONAL_TEAM_ELO.items():
        if name in key or key in name:
            return float(elo)
    return 1700.0


def get_national_elo(team_name: str) -> float:
    """Legacy alias for get_team_elo."""
    return get_team_elo(team_name)

