# Case-Insensitive Team Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement robust, case-insensitive team name mapping and normalization across the application to handle naming variations and capitalization issues when querying matches and matching against Kalshi markets.

**Architecture:** Create a new module `src/data/team_mapping.py` that houses team alias dictionaries, standardizes names, and provides matching logic. Integrate this normalization layer across predictor pipelines, scraper lookups, ELO retrieval, and market parsers.

**Tech Stack:** Python 3, Regular Expressions

## Global Constraints
- Do not introduce external fuzzy matching packages (like `fuzzywuzzy`); keep dependencies standard.
- Ensure all normalization functions are case-insensitive.
- Preserve existing scraper functionality and fallbacks.

---

### Task 1: Scaffolding and Team Mapping Logic

**Files:**
- Create: `src/data/team_mapping.py`
- Test: `scratch/test_team_mapping.py`

**Interfaces:**
- Produces: 
  - `normalize_team_name(name: str) -> str`: standardizes country names to the lowercase keys expected by the internal ELO database and FBRef scoring priors.
  - `is_team_match(team: str, text: str) -> bool`: checks if a team name matches a given string/market title.

- [ ] **Step 1: Create `src/data/team_mapping.py` with alias mapping and helpers**

```python
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
```

- [ ] **Step 2: Create a scratch unit test script `scratch/test_team_mapping.py`**

```python
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.team_mapping import normalize_team_name, is_team_match

def run_tests():
    # Test normalization
    assert normalize_team_name("Korea Republic") == "south korea"
    assert normalize_team_name("south korea") == "south korea"
    assert normalize_team_name("United States") == "usa"
    assert normalize_team_name("usa") == "usa"
    assert normalize_team_name("Czechia") == "czech republic"
    
    # Test matching
    assert is_team_match("South Korea", "Korea Republic Winner?") == True
    assert is_team_match("South Korea", "KXWCGAME-26JUN24RSAKOR-KOR") == False  # Suffixes should not match blindly, but event titles will
    assert is_team_match("South Africa", "South Africa vs Korea Republic") == True
    assert is_team_match("South Korea", "South Africa vs Korea Republic") == True
    
    print("ALL TEAM MAPPING TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
```

- [ ] **Step 3: Run the test script to verify it passes**

Run: `python scratch/test_team_mapping.py`
Expected output: `ALL TEAM MAPPING TESTS PASSED SUCCESSFULLY!`

- [ ] **Step 4: Commit the mapping scaffolding**

```bash
git add src/data/team_mapping.py scratch/test_team_mapping.py
git commit -m "feat: add case-insensitive team normalization and matching layer"
```

---

### Task 2: Integrations in Scrapers and Models

**Files:**
- Modify: `src/data/scrapers/elo_db.py`
- Modify: `src/data/scrapers/fbref.py`
- Modify: `src/predictor.py`

- [ ] **Step 1: Update ELO database queries to use team normalization**

Modify `src/data/scrapers/elo_db.py` to import `normalize_team_name` and apply it at the beginning of `get_national_elo`.

```python
# In src/data/scrapers/elo_db.py
from src.data.team_mapping import normalize_team_name

# Replace get_national_elo
def get_national_elo(team_name: str) -> float:
    """Return ELO for a national team."""
    key = normalize_team_name(team_name)
    if key in NATIONAL_TEAM_ELO:
        return float(NATIONAL_TEAM_ELO[key])
    # Fuzzy match
    for name, elo in NATIONAL_TEAM_ELO.items():
        if name in key or key in name:
            return float(elo)
    return 1700.0
```

- [ ] **Step 2: Update FBRef scoring priors queries to use team normalization**

Modify `src/data/scrapers/fbref.py` to import `normalize_team_name` and apply it in `get_team_data`.

```python
# In src/data/scrapers/fbref.py
from src.data.team_mapping import normalize_team_name

# Inside get_team_data:
def get_team_data(team_name: str) -> dict:
    """
    Retrieves team form, ELO, and scoring averages.
    """
    name_lower = normalize_team_name(team_name)
    # Rest of the function continues as before, checking INTL_SCORING_PRIORS using name_lower
```

- [ ] **Step 3: Update `predict_match` entrypoint in `src/predictor.py`**

Modify `src/predictor.py` to import `normalize_team_name` and apply it to home and away inputs.

```python
# In src/predictor.py
from src.data.team_mapping import normalize_team_name

# Inside predict_match:
def predict_match(home_team: str, away_team: str, kalshi_probs: dict = None, neutral: bool = True) -> PredictionResult:
    home_lower = normalize_team_name(home_team)
    away_lower = normalize_team_name(away_team)
    # Rest of the function continues as before
```

- [ ] **Step 4: Commit task changes**

```bash
git add src/data/scrapers/elo_db.py src/data/scrapers/fbref.py src/predictor.py
git commit -m "feat: integrate team normalization into scrapers, ELO databases, and predictions"
```

---

### Task 3: Integrations in CLI commands (`main.py`)

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Import helpers and apply to `run_predict`**

Modify `main.py` to import `normalize_team_name` and `is_team_match`.
In `run_predict(query: str)`, normalize `home` and `away` inputs, and update the Kalshi market matching logic.

```python
# In main.py, near top imports:
from src.data.team_mapping import normalize_team_name, is_team_match

# In run_predict(query: str):
    home, away = parts[0].strip(), parts[1].strip()
    home = normalize_team_name(home)
    away = normalize_team_name(away)
    console.print(f"\n[cyan]Predicting match: {home.title()} vs {away.title()}...[/cyan]")
    
    # Run public search on Kalshi for current prices to serve as feature input
    client = KalshiClient()
    markets = client.get_soccer_markets()
    
    kalshi_probs = None
    for ev in markets:
        title = ev["event_title"].lower()
        if " vs " in title:
            t_parts = title.split(" vs ")
            t_home = normalize_team_name(t_parts[0])
            t_away = normalize_team_name(t_parts[1])
            if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                # Map probabilities
                probs = {}
                for m in ev["markets"]:
                    t = m["title"].lower()
                    if is_team_match(home, t):
                        probs["home_win"] = m["yes_price"]
                    elif is_team_match(away, t):
                        probs["away_win"] = m["yes_price"]
                    elif "draw" in t or "tie" in t:
                        probs["draw"] = m["yes_price"]
                if len(probs) >= 2:
                    kalshi_probs = probs
                    break
```

- [ ] **Step 2: Update game lines and player prop loops in `run_predict`**

Update the Game Lines and Player Props loops in `run_predict` to use normalized event matching:

```python
    # Under Game Lines:
    for outcome, label, prob in [("over_1.5", "Over 1.5 Goals", over_15_prob), 
                                 ("over_2.5", "Over 2.5 Goals", over_25_prob), 
                                 ("btts", "Both Teams to Score", btts_prob)]:
        live_p = None
        for ev in markets:
            title = ev["event_title"].lower()
            if " vs " in title:
                t_parts = title.split(" vs ")
                t_home = normalize_team_name(t_parts[0])
                t_away = normalize_team_name(t_parts[1])
                if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                    for m in ev["markets"]:
                        t = m["title"].lower()
                        if outcome == "over_1.5" and "over 1.5" in t:
                            live_p = m["yes_price"]
                        elif outcome == "over_2.5" and "over 2.5" in t:
                            live_p = m["yes_price"]
                        elif outcome == "btts" and "both teams" in t:
                            live_p = m["yes_price"]
```

And similarly for Player Props:
```python
    # Under Player Props:
    for name, p_prob, is_home in players:
        live_p = None
        for ev in markets:
            title = ev["event_title"].lower()
            if " vs " in title:
                t_parts = title.split(" vs ")
                t_home = normalize_team_name(t_parts[0])
                t_away = normalize_team_name(t_parts[1])
                if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                    for m in ev["markets"]:
                        t = m["title"].lower()
                        if name in t and ("score" in t or "goal" in t):
                            live_p = m["yes_price"]
```

- [ ] **Step 3: Update `run_ask` command in `main.py`**

Replicate the exact same normalization and event/market title matching logic in `run_ask(query: str, user_model: str)`.

- [ ] **Step 4: Run verification prediction**

Run: `python main.py predict "south africa vs south korea"`
Verify:
1. The forecast matrix prints South Africa, Draw, and South Korea probabilities successfully.
2. The Kalshi Price column prints numeric values (not `N/A`) for Moneyline, Game Lines, and Player Props.
3. The Predict Portfolio Bot Paper Bets panel shows active positions placed by Big D and SIGMABALLS.

- [ ] **Step 5: Commit and clean up**

```bash
git add main.py
git commit -m "feat: complete end-to-end team normalization integration in CLI commands"
```
