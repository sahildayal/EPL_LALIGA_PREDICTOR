import re

TEAM_ALIASES = {
    # Common 2-letter and 3-letter abbreviations / acronyms
    "sk": "south korea",
    "sa": "south africa",
    "nk": "north korea",
    "eng": "england",
    "fra": "france",
    "arg": "argentina",
    "bra": "brazil",
    "por": "portugal",
    "esp": "spain",
    "ger": "germany",
    "ned": "netherlands",
    "cro": "croatia",
    "ita": "italy",
    "mor": "morocco",
    "mar": "morocco",
    "uru": "uruguay",
    "col": "colombia",
    "mex": "mexico",
    "jpn": "japan",
    "aus": "australia",
    "irn": "iran",
    "can": "canada",
    "ecu": "ecuador",
    "sco": "scotland",
    "pol": "poland",
    "tur": "turkey",
    "nz": "new zealand",
    "nzl": "new zealand",
    "bel": "belgium",
    "den": "denmark",
    "sui": "switzerland",
    "sen": "senegal",
    "nga": "nigeria",
    "egy": "egypt",
    "chi": "chile",
    "per": "peru",
    "aut": "austria",
    "wal": "wales",
    "irl": "republic of ireland",
    "cze": "czech republic",
    "svk": "slovakia",
    "hun": "hungary",
    "rou": "romania",
    "ukr": "ukraine",
    "rus": "russia",
    "srb": "serbia",
    "swe": "sweden",
    "nor": "norway",
    "fin": "finland",
    "gre": "greece",
    "alb": "albania",
    "geo": "georgia",
    "par": "paraguay",
    "ven": "venezuela",
    "bol": "bolivia",
    "crc": "costa rica",
    "pan": "panama",
    "hon": "honduras",
    "slv": "el salvador",
    "cmr": "cameroon",
    "gha": "ghana",
    "civ": "ivory coast",
    "mli": "mali",
    "alg": "algeria",
    "tun": "tunisia",
    "rsa": "south africa",
    "ksa": "saudi arabia",
    "qat": "qatar",
    "irq": "iraq",
    "jor": "jordan",
    "uzb": "uzbekistan",
    "chn": "china",
    "ind": "india",
    "jam": "jamaica",
    "dprk": "north korea",
    "uae": "uae",
    "usa": "usa",

    # Naming variations and standardizations
    "korea republic": "south korea",
    "korea": "south korea",
    "republic of korea": "south korea",
    "south korea": "south korea",
    
    "north korea": "north korea",
    "democratic people's republic of korea": "north korea",
    "dpr korea": "north korea",
    
    "united states": "usa",
    "united states of america": "usa",
    "us of a": "usa",
    
    "czechia": "czech republic",
    "czech": "czech republic",
    "czech republic": "czech republic",
    
    "türkiye": "turkey",
    "turkiye": "turkey",
    "turkey": "turkey",
    
    "côte d'ivoire": "ivory coast",
    "cote d'ivoire": "ivory coast",
    "ivory coast": "ivory coast",
    
    "ireland": "republic of ireland",
    "republic of ireland": "republic of ireland",
    
    "northern ireland": "northern ireland",
    
    "bosnia and herzegovina": "bosnia-herzegovina",
    "bosnia": "bosnia-herzegovina",
    "herzegovina": "bosnia-herzegovina",
    "bosnia-herzegovina": "bosnia-herzegovina",
    
    "curaçao": "curacao",
    "curacao": "curacao",
    
    "democratic republic of the congo": "congo dr",
    "dr congo": "congo dr",
    "congo dr": "congo dr",
    "congo": "congo",
    
    "united arab emirates": "uae",
    
    "ir iran": "iran",
    
    "republic of south africa": "south africa",
    
    "south sudan": "south sudan",
    "sudan": "sudan",
    
    "american samoa": "american samoa",
    "samoa": "samoa",
    
    "british virgin islands": "british virgin islands",
    "us virgin islands": "us virgin islands",
    "virgin islands": "virgin islands",
    
    "north macedonia": "north macedonia",
    "macedonia": "macedonia",
    
    "northern cyprus": "northern cyprus",
    "cyprus": "cyprus",
    
    "guinea-bissau": "guinea-bissau",
    "equatorial guinea": "equatorial guinea",
    "papua new guinea": "papua new guinea",
    "new guinea": "papua new guinea",
    "guinea": "guinea",
}

# Precompute alias mapping and sorted order at module level
from src.data.scrapers.elo_db import NATIONAL_TEAM_ELO

ALL_ALIASES_MAP = {}
for alias, canonical in TEAM_ALIASES.items():
    ALL_ALIASES_MAP[alias] = canonical
    ALL_ALIASES_MAP[canonical] = canonical

for team in NATIONAL_TEAM_ELO.keys():
    t_norm = team.lower().strip()
    if t_norm not in ALL_ALIASES_MAP:
        ALL_ALIASES_MAP[t_norm] = t_norm

ALIASES_SORTED = sorted(ALL_ALIASES_MAP.keys(), key=len, reverse=True)

ALIASES_PATTERNS = {
    alias: re.compile(r'(?<!\w)' + re.escape(alias) + r'(?!\w)')
    for alias in ALIASES_SORTED
}

def normalize_team_name(name: str) -> str:
    """Standardizes a country name to its lowercase canonical form."""
    if not name:
        return ""
    name_clean = name.lower().strip()
    
    # Remove question marks
    name_clean = name_clean.replace("?", "")
    
    # Use word boundaries to strip common suffixes/terms: winner, to win, win, to score, goal
    name_clean = re.sub(r'\b(winner|to win|win|to score|goal)\b', '', name_clean)
    
    # Collapse multiple spaces and strip
    name_clean = re.sub(r'\s+', ' ', name_clean).strip()
    
    return TEAM_ALIASES.get(name_clean, name_clean)

def is_team_match(team: str, text: str) -> bool:
    """Robustly checks if a team name is referenced in a market title/text."""
    t_norm = normalize_team_name(team)
    txt_norm = normalize_team_name(text)
    
    if not t_norm or not txt_norm:
        return False
        
    if t_norm == txt_norm:
        return True
        
    # Find all non-overlapping matches in txt_norm using precompiled patterns
    matched_intervals = [] # list of tuples: (start_idx, end_idx, canonical_name)
    
    for alias in ALIASES_SORTED:
        canonical = ALL_ALIASES_MAP[alias]
        pattern = ALIASES_PATTERNS[alias]
        for match in pattern.finditer(txt_norm):
            start, end = match.start(), match.end()
            # Check for overlap with any existing matched intervals
            overlap = False
            for m_start, m_end, _ in matched_intervals:
                if not (end <= m_start or start >= m_end):
                    overlap = True
                    break
            if not overlap:
                matched_intervals.append((start, end, canonical))
                
    # Get all canonical names that were successfully matched in the text
    matched_canonicals = {canonical for _, _, canonical in matched_intervals}
    return t_norm in matched_canonicals
