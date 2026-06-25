import re

TEAM_ALIASES = {
    "korea republic": "south korea",
    "korea": "south korea",
    "republic of korea": "south korea",
    "south korea": "south korea",
    
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
    
    "bosnia and herzegovina": "bosnia-herzegovina",
    "bosnia": "bosnia-herzegovina",
    "herzegovina": "bosnia-herzegovina",
    "bosnia-herzegovina": "bosnia-herzegovina",
    
    "curaçao": "curacao",
    "curacao": "curacao",
    
    "democratic republic of the congo": "congo dr",
    "dr congo": "congo dr",
    "congo dr": "congo dr",
    "congo": "congo dr",
    
    "united arab emirates": "uae",
    "uae": "uae",
    
    "ir iran": "iran",
    "iran": "iran",
    
    "republic of south africa": "south africa",
    "south africa": "south africa",
}

def normalize_team_name(name: str) -> str:
    """Standardizes a country name to its lowercase canonical form."""
    if not name:
        return ""
    name_clean = name.lower().strip()
    name_clean = re.sub(r'\s+', ' ', name_clean)
    name_clean = name_clean.replace("?", "").replace("winner", "").replace("win", "").strip()
    return TEAM_ALIASES.get(name_clean, name_clean)

def is_team_match(team: str, text: str) -> bool:
    """Robustly checks if a team name is referenced in a market title/text."""
    t_norm = normalize_team_name(team)
    txt_norm = normalize_team_name(text)
    
    if t_norm == txt_norm:
        return True
        
    # Replace all aliases in text with their canonical forms to allow substring matching
    for alias, canonical in TEAM_ALIASES.items():
        if alias in txt_norm:
            txt_norm = txt_norm.replace(alias, canonical)
            
    if t_norm in txt_norm:
        return True
        
    return False
