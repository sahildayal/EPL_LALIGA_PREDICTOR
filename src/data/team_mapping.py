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
    # Premier League & La Liga Club Aliases
    "manc": "manchester city",
    "man city": "manchester city",
    "mc": "manchester city",
    "manu": "manchester united",
    "man utd": "manchester united",
    "man united": "manchester united",
    "mu": "manchester united",
    "tot": "tottenham",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "ars": "arsenal",
    "che": "chelsea",
    "liv": "liverpool",
    "nwc": "newcastle",
    "newcastle united": "newcastle",
    "avl": "aston villa",
    "villa": "aston villa",
    "whu": "west ham",
    "west ham united": "west ham",
    "wol": "wolverhampton",
    "wolves": "wolverhampton",
    "wolverhampton wanderers": "wolverhampton",
    "nfo": "nottingham forest",
    "forest": "nottingham forest",
    "bha": "brighton",
    "brighton & hove albion": "brighton",
    "bou": "bournemouth",
    "afc bournemouth": "bournemouth",
    "cry": "crystal palace",
    "palace": "crystal palace",
    "eve": "everton",
    "ful": "fulham",
    "bre": "brentford",
    "lei": "leicester",
    "leicester city": "leicester",
    "sou": "southampton",
    "ips": "ipswich",
    "ipswich town": "ipswich",

    # La Liga
    "rma": "real madrid",
    "madrid": "real madrid",
    "bar": "barcelona",
    "barca": "barcelona",
    "fc barcelona": "barcelona",
    "atm": "atletico madrid",
    "atletico": "atletico madrid",
    "atlético": "atletico madrid",
    "atlétic madrid": "atletico madrid",
    "ath": "athletic bilbao",
    "athletic": "athletic bilbao",
    "athletic club": "athletic bilbao",
    "rso": "real sociedad",
    "la real": "real sociedad",
    "vil": "villarreal",
    "bet": "real betis",
    "betis": "real betis",
    "sev": "sevilla",
    "gir": "girona",
    "osa": "osasuna",
    "cel": "celta vigo",
    "celta": "celta vigo",
    "ray": "rayo vallecano",
    "mlo": "mallorca",
    "lpa": "las palmas",
    "ala": "alaves",
    "alavés": "alaves",
    "get": "getafe",
    "esp": "espanyol",
    "leg": "leganes",
    "vll": "real valladolid",
    "valladolid": "real valladolid",

    # Other UCL European Clubs
    "bayern": "bayern munich",
    "fc bayern": "bayern munich",
    "psg": "paris saint-germain",
    "paris sg": "paris saint-germain",
    "dortmund": "borussia dortmund",
    "bvb": "borussia dortmund",
    "leverkusen": "bayer leverkusen",
    "bayer 04": "bayer leverkusen",
    "inter": "inter milan",
    "internazionale": "inter milan",
    "milan": "ac milan",
    "juve": "juventus",
    "leipzig": "rb leipzig",
    "sporting": "sporting cp",
}

TEAM_COMPETITION = {
    # Premier League
    "arsenal": "epl", "manchester city": "epl", "man city": "epl", "liverpool": "epl", "chelsea": "epl",
    "tottenham": "epl", "spurs": "epl", "manchester united": "epl", "man united": "epl", "man utd": "epl",
    "aston villa": "epl", "newcastle": "epl", "brighton": "epl", "west ham": "epl", "fulham": "epl",
    "bournemouth": "epl", "brentford": "epl", "crystal palace": "epl", "everton": "epl", "wolverhampton": "epl",
    "wolves": "epl", "nottingham forest": "epl", "forest": "epl", "leicester": "epl", "southampton": "epl",
    "ipswich": "epl",

    # La Liga
    "real madrid": "laliga", "barcelona": "laliga", "atletico madrid": "laliga", "atletico": "laliga",
    "girona": "laliga", "athletic bilbao": "laliga", "athletic club": "laliga", "real sociedad": "laliga",
    "villarreal": "laliga", "real betis": "laliga", "betis": "laliga", "sevilla": "laliga", "osasuna": "laliga",
    "celta vigo": "laliga", "rayo vallecano": "laliga", "mallorca": "laliga", "las palmas": "laliga",
    "alaves": "laliga", "getafe": "laliga", "espanyol": "laliga", "leganes": "laliga", "real valladolid": "laliga",
    "valladolid": "laliga",

    # UCL Other European Giants
    "bayern munich": "ucl", "bayern": "ucl", "psg": "ucl", "paris saint-germain": "ucl",
    "inter milan": "ucl", "inter": "ucl", "bayer leverkusen": "ucl", "leverkusen": "ucl",
    "borussia dortmund": "ucl", "dortmund": "ucl", "atalanta": "ucl", "juventus": "ucl",
    "rb leipzig": "ucl", "leipzig": "ucl", "sporting cp": "ucl", "sporting": "ucl",
    "ac milan": "ucl", "milan": "ucl", "benfica": "ucl", "porto": "ucl",
}

def get_match_league(home_team: str, away_team: str, user_league: str = None) -> str:
    """
    Determines the league context for a match query.
    If user_league is explicitly provided and valid, returns it.
    Otherwise auto-detects based on team affiliations (epl, laliga, or cross-league ucl).
    """
    if user_league and user_league.lower().strip() in ["epl", "laliga", "ucl"]:
        return user_league.lower().strip()
        
    h_norm = normalize_team_name(home_team)
    a_norm = normalize_team_name(away_team)
    
    h_comp = TEAM_COMPETITION.get(h_norm)
    a_comp = TEAM_COMPETITION.get(a_norm)
    
    # Cross-league match (e.g., EPL team vs La Liga team) or explicit UCL club -> Champions League
    if h_comp == "ucl" or a_comp == "ucl":
        return "ucl"
    if h_comp and a_comp and h_comp != a_comp:
        return "ucl"
    if h_comp:
        return h_comp
    if a_comp:
        return a_comp
        
    return "epl"

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
        
    # If the team name is not a known country/team alias, perform fallback word-boundary match
    if t_norm not in ALL_ALIASES_MAP:
        pattern = re.compile(r'(?<!\w)' + re.escape(t_norm) + r'(?!\w)')
        if pattern.search(txt_norm):
            return True
        return False
        
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
