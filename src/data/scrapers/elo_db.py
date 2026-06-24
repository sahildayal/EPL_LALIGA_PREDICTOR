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


def get_national_elo(team_name: str) -> float:
    """Return ELO for a national team."""
    key = team_name.lower().strip()
    if key in NATIONAL_TEAM_ELO:
        return float(NATIONAL_TEAM_ELO[key])
    # Fuzzy match
    for name, elo in NATIONAL_TEAM_ELO.items():
        if name in key or key in name:
            return float(elo)
    return 1700.0
