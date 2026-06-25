import re

TEAM_ALIASES = {
    "korea republic": "south korea",
    "korea": "south korea",
    "republic of korea": "south korea",
    "south korea": "south korea",
    
    "north korea": "north korea",
    "democratic people's republic of korea": "north korea",
    "dpr korea": "north korea",
    "dprk": "north korea",
    
    "united states": "usa",
    "united states of america": "usa",
    "us of a": "usa",
    "usa": "usa",
    
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
    
    "united arab emirates": "uae",
    "uae": "uae",
    
    "ir iran": "iran",
    "iran": "iran",
    
    "republic of south africa": "south africa",
    "south africa": "south africa",
    
    # Preventing potential country collisions for other similar names
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
ALL_ALIASES_MAP = {}
for alias, canonical in TEAM_ALIASES.items():
    ALL_ALIASES_MAP[alias] = canonical
    ALL_ALIASES_MAP[canonical] = canonical

ALIASES_SORTED = sorted(ALL_ALIASES_MAP.keys(), key=len, reverse=True)

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
        
    # Get the aliases mapping and sorted list to use.
    # In the rare event that the query team's normalized name isn't already 
    # in the precomputed map, we fall back to a dynamic map.
    if t_norm not in ALL_ALIASES_MAP:
        aliases_map = ALL_ALIASES_MAP.copy()
        aliases_map[t_norm] = t_norm
        aliases_sorted = sorted(aliases_map.keys(), key=len, reverse=True)
    else:
        aliases_map = ALL_ALIASES_MAP
        aliases_sorted = ALIASES_SORTED
        
    # Find all non-overlapping matches in txt_norm using word boundaries
    matched_intervals = [] # list of tuples: (start_idx, end_idx, canonical_name)
    
    for alias in aliases_sorted:
        canonical = aliases_map[alias]
        # Match using word boundaries.
        pattern = r'(?<!\w)' + re.escape(alias) + r'(?!\w)'
        for match in re.finditer(pattern, txt_norm):
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
    
    # Check if the query team's canonical name is in the matched canonical names
    if t_norm in matched_canonicals:
        return True
        
    return False
