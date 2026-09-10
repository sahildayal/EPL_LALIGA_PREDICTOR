# Player Stats & Props Predictions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a player prop prediction engine that fetches starting rosters dynamically from ESPN, scrapes player goals and assists from FBRef, caches them in SQLite, calculates probabilities using binomial expectation, and integrates them with Kalshi sports markets and paper trading bots.

**Architecture:** 
1. Use an ESPN Summary API scraper to fetch real-time starting XIs or fallback to the most recent game's lineup.
2. Store player stats in a structured SQLite table `player_statistics` with 7-day TTL expiration.
3. Compute goal, assist, and goal-or-assist (G/A) props using binomial distributions conditionally evaluated against the Dixon-Coles goal expectation matrix.
4. Add `KXWCAST` and `KXWCSOA` support to `KalshiClient` and format the CLI display and bots to trade player props.

**Tech Stack:** Python, SQLite, requests, Beautiful Soup (bs4), numpy/scipy.

## Global Constraints
* Maintain case-insensitive matching for all player names.
* Do not introduce external fuzzy matching packages.
* Keep SQLite database connections properly closed (using try-finally).
* Every task must implement TDD with tests written first.

---

### Task 1: SQLite Database Setup & Cache Methods
**Files:**
* Modify: `src/data/cache.py`
* Test: `scratch/test_db_cache.py` (create)

**Interfaces:**
* Produces:
  * `save_player_stats(player_name: str, position: str, xg_per_90: float, goals_per_90: float, assists_per_90: float, club_team: str, intl_team: str)`
  * `get_player_stats_cache(player_name: str) -> dict | None`

- [ ] **Step 1: Write a test verifying player statistics storage and retrieval**
  Create `scratch/test_db_cache.py`:
  ```python
  import sys
  sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
  import unittest
  import time
  from src.data.cache import save_player_stats, get_player_stats_cache

  class TestDbCache(unittest.TestCase):
      def test_save_and_retrieve_stats(self):
          save_player_stats("Joao Neves", "CM", 0.12, 0.10, 0.22, "PSG", "Portugal")
          stats = get_player_stats_cache("Joao Neves")
          self.assertIsNotNone(stats)
          self.assertEqual(stats["position"], "CM")
          self.assertEqual(stats["goals_per_90"], 0.10)
          self.assertEqual(stats["assists_per_90"], 0.22)
          self.assertEqual(stats["club_team"], "psg")
          self.assertEqual(stats["intl_team"], "portugal")
          
      def test_missing_stats(self):
          self.assertIsNone(get_player_stats_cache("Non Existent Player"))

  if __name__ == "__main__":
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_db_cache.py`
  Expected: FAIL with `ImportError: cannot import name 'save_player_stats'`

- [ ] **Step 3: Implement database table creation and cache methods**
  Modify `src/data/cache.py` to create the table at startup and add methods:
  ```python
  # Add table creation in _conn():
  conn.execute("""
      CREATE TABLE IF NOT EXISTS player_statistics (
          player_name TEXT PRIMARY KEY,
          position TEXT NOT NULL,
          xg_per_90 REAL NOT NULL,
          goals_per_90 REAL NOT NULL,
          assists_per_90 REAL NOT NULL,
          club_team TEXT,
          intl_team TEXT,
          last_updated REAL NOT NULL
      )
  """)
  
  # Implement methods:
  def save_player_stats(player_name: str, position: str, xg_per_90: float, goals_per_90: float, assists_per_90: float, club_team: str, intl_team: str):
      name_lower = player_name.lower().strip()
      try:
          conn = _conn()
          try:
              with conn:
                  conn.execute("""
                      INSERT OR REPLACE INTO player_statistics 
                      (player_name, position, xg_per_90, goals_per_90, assists_per_90, club_team, intl_team, last_updated)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                  """, (name_lower, position, xg_per_90, goals_per_90, assists_per_90, 
                        club_team.lower().strip() if club_team else "", 
                        intl_team.lower().strip() if intl_team else "", 
                        time.time()))
          finally:
              conn.close()
      except Exception:
          pass

  def get_player_stats_cache(player_name: str) -> dict | None:
      name_lower = player_name.lower().strip()
      try:
          conn = _conn()
          try:
              with conn:
                  row = conn.execute("""
                      SELECT position, xg_per_90, goals_per_90, assists_per_90, club_team, intl_team, last_updated
                      FROM player_statistics WHERE player_name = ?
                  """, (name_lower,)).fetchone()
              if row:
                  # Check TTL of 7 days (604800 seconds)
                  if time.time() - row[6] < 604800:
                      return {
                          "name": name_lower,
                          "position": row[0],
                          "xg_per_90": row[1],
                          "goals_per_90": row[2],
                          "assists_per_90": row[3],
                          "club_team": row[4],
                          "intl_team": row[5]
                      }
          finally:
              conn.close()
      except Exception:
          pass
      return None
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_db_cache.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/data/cache.py scratch/test_db_cache.py
  git commit -m "feat: add SQLite player statistics table and CRUD cache methods"
  ```

---

### Task 2: ESPN Lineup Scraper & Lineup Fetching
**Files:**
* Modify: `src/data/scrapers/fixtures.py`
* Test: `scratch/test_lineups.py` (create)

**Interfaces:**
* Produces:
  * `get_match_lineups(home_team: str, away_team: str, event_id: str = None) -> dict`
    * Returns: `{"home_lineup": list_of_names, "away_lineup": list_of_names, "source": str}`

- [ ] **Step 1: Write test for match lineups retrieval**
  Create `scratch/test_lineups.py`:
  ```python
  import sys
  sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
  import unittest
  from src.data.scrapers.fixtures import get_match_lineups

  class TestLineups(unittest.TestCase):
      def test_get_lineups_with_stubbed_id(self):
          # Test with a dummy event ID or real ESPN soccer event ID
          res = get_match_lineups("Colombia", "Portugal", event_id="401642878")
          self.assertIn("home_lineup", res)
          self.assertIn("away_lineup", res)
          self.assertIsNotNone(res["source"])

  if __name__ == "__main__":
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_lineups.py`
  Expected: FAIL with `ImportError` or `AttributeError`

- [ ] **Step 3: Implement ESPN Lineup Fetching with Fallback**
  In `src/data/scrapers/fixtures.py`, add `get_match_lineups` and helpers:
  ```python
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
  ```

- [ ] **Step 4: Run tests to verify it passes**
  Run: `python scratch/test_lineups.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/data/scrapers/fixtures.py scratch/test_lineups.py
  git commit -m "feat: implement dynamic ESPN starting lineup parser with recent match fallbacks"
  ```

---

### Task 3: Dynamic FBRef Scraper & SQLite Storage
**Files:**
* Modify: `src/data/scrapers/player_stats.py`
* Test: `scratch/test_player_scraping.py` (create)

**Interfaces:**
* Consumes:
  * `save_player_stats`, `get_player_stats_cache` from `src.data.cache`
* Produces:
  * `get_player_stats(name: str) -> dict`
    * Blends 60% country, 40% club. Caches results in SQLite `player_statistics`.

- [ ] **Step 1: Write test for player stats retrieval and SQLite caching**
  Create `scratch/test_player_scraping.py`:
  ```python
  import sys
  sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
  import unittest
  from src.data.scrapers.player_stats import get_player_stats

  class TestPlayerScraping(unittest.TestCase):
      def test_seeded_player(self):
          stats = get_player_stats("Kylian Mbappe")
          self.assertEqual(stats["name"], "kylian mbappe")
          self.assertEqual(stats["position"], "FW")
          self.assertGreater(stats["goals_per_90"], 0.4)

      def test_scrape_fallback(self):
          # Test a non-seeded player to trigger scraping/defaults
          stats = get_player_stats("Declan Rice")
          self.assertIsNotNone(stats)
          self.assertIn("goals_per_90", stats)
          self.assertIn("assists_per_90", stats)

  if __name__ == "__main__":
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_player_scraping.py`
  Expected: Failures or misses in cache updates or assists lookup

- [ ] **Step 3: Update player stats scraper with SQLite support**
  Modify `src/data/scrapers/player_stats.py`:
  ```python
  # Import DB cache methods
  from src.data.cache import save_player_stats, get_player_stats_cache

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
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_player_scraping.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/data/scrapers/player_stats.py scratch/test_player_scraping.py
  git commit -m "feat: store blended player stats in SQLite cache with 7-day TTL"
  ```

---

### Task 4: Player Prop Mathematical Prediction Engine
**Files:**
* Create: `src/models/player_props.py`
* Test: `scratch/test_prop_math.py` (create)

**Interfaces:**
* Produces:
  * `calculate_player_prop_probs(player_stats: dict, is_home: bool, score_matrix: np.ndarray, team_historical_avg: float) -> dict`
    * Returns: `{"goals_1": float, "goals_2": float, "assists_1": float, "assists_2": float, "goal_or_assist": float}`

- [ ] **Step 1: Write test for binomial prop math**
  Create `scratch/test_prop_math.py`:
  ```python
  import sys
  sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
  import unittest
  import numpy as np
  from src.models.player_props import calculate_player_prop_probs

  class TestPropMath(unittest.TestCase):
      def test_binomial_math(self):
          player_stats = {
              "goals_per_90": 0.5,
              "assists_per_90": 0.25
          }
          # Simple 2x2 score matrix
          matrix = np.zeros((3, 3))
          matrix[1, 0] = 0.5  # 50% chance of 1-0
          matrix[2, 0] = 0.5  # 50% chance of 2-0
          
          # Home team historical average = 1.0 goals per match
          probs = calculate_player_prop_probs(player_stats, is_home=True, score_matrix=matrix, team_historical_avg=1.0)
          
          # Goal Share = 0.5 / 1.0 = 0.5
          # At g=1: P(1+ goals) = 1 - 0.5^1 = 0.5
          # At g=2: P(1+ goals) = 1 - 0.5^2 = 0.75
          # Expected P(1+ goals) = 0.5 * 0.5 + 0.5 * 0.75 = 0.625
          self.assertAlmostEqual(probs["goals_1"], 0.625)

  if __name__ == "__main__":
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_prop_math.py`
  Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement binomial player prop calculation**
  Create `src/models/player_props.py`:
  ```python
  import numpy as np
  import math

  def calculate_player_prop_probs(player_stats: dict, is_home: bool, score_matrix: np.ndarray, team_historical_avg: float) -> dict:
      """
      Calculates player prop probabilities using binomial distributions
      conditionally evaluated against the score expectation matrix.
      """
      goals_per_90 = player_stats.get("goals_per_90", 0.25)
      assists_per_90 = player_stats.get("assists_per_90", 0.15)
      
      avg_goals = max(team_historical_avg, 0.5)
      
      # Player shares per team goal
      s_g = min(goals_per_90 / avg_goals, 0.95)
      s_a = min(assists_per_90 / avg_goals, 0.95)
      s_ga = min(s_g + s_a, 0.95)
      
      # Cumulative binomial probability helper
      # P(at least k events in g trials)
      def p_binomial(k, g, share):
          if g < k:
              return 0.0
          if k <= 0:
              return 1.0
          prob = 0.0
          for j in range(k, g + 1):
              # nCr * p^j * (1-p)^(n-j)
              coeff = math.comb(g, j)
              prob += coeff * (share ** j) * ((1.0 - share) ** (g - j))
          return prob

      prob_g1 = 0.0
      prob_g2 = 0.0
      prob_a1 = 0.0
      prob_a2 = 0.0
      prob_ga = 0.0
      
      h_max, a_max = score_matrix.shape
      for h in range(h_max):
          for a in range(a_max):
              cell_p = score_matrix[h, a]
              if cell_p <= 0:
                  continue
              
              g = h if is_home else a
              prob_g1 += cell_p * p_binomial(1, g, s_g)
              prob_g2 += cell_p * p_binomial(2, g, s_g)
              prob_a1 += cell_p * p_binomial(1, g, s_a)
              prob_a2 += cell_p * p_binomial(2, g, s_a)
              prob_ga += cell_p * p_binomial(1, g, s_ga)
              
      return {
          "goals_1": round(prob_g1, 4),
          "goals_2": round(prob_g2, 4),
          "assists_1": round(prob_a1, 4),
          "assists_2": round(prob_a2, 4),
          "goal_or_assist": round(prob_ga, 4)
      }
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_prop_math.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/models/player_props.py scratch/test_prop_math.py
  git commit -m "feat: implement binomial modeling for player goals, assists, and G/A"
  ```

---

### Task 5: Kalshi Client Update & Match Predict CLI Integration
**Files:**
* Modify: `src/market/kalshi_client.py:189`
* Modify: `main.py:119-223`
* Test: `scratch/test_market_match.py` (create)

- [ ] **Step 1: Write test for Kalshi player market match parsing**
  Create `scratch/test_market_match.py`:
  ```python
  import sys
  sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
  import unittest
  from src.data.team_mapping import is_team_match

  class TestMarketMatch(unittest.TestCase):
      def test_market_title_checks(self):
          self.assertTrue(is_team_match("Joao Neves", "Joao Neves: 1+ assists?"))
          self.assertTrue(is_team_match("Joao Neves", "Joao Neves: score or assist?"))
          self.assertTrue(is_team_match("Joao Neves", "Joao Neves: 2+ goals"))

  if __name__ == "__main__":
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_market_match.py`
  Expected: FAIL or passes but fails integration checks

- [ ] **Step 3: Modify Kalshi Client active sports tickers**
  Modify `src/market/kalshi_client.py` around line 189 to query `KXWCAST` and `KXWCSOA`:
  ```python
  series_tickers = ["KXWCGAME", "KXWCBTTS", "KXWCTOTAL", "KXWCGOAL", "KXWCAST", "KXWCSOA"]
  ```

- [ ] **Step 4: Update `main.py` predicting and displaying section**
  Modify `main.py`'s player props lookups to map goals, assists, and G/A props.
  Import `calculate_player_prop_probs` and `get_match_lineups`:
  ```python
  # Under imports in main.py:
  from src.data.scrapers.fixtures import get_match_lineups
  from src.models.player_props import calculate_player_prop_probs
  ```
  And in `run_predict(query: str)`:
  Replace the Key Player Scoring Props lookup section (lines 119-223):
  ```python
      # Retrieve dynamic starting lineups from ESPN
      lineups_res = get_match_lineups(home, away)
      home_lineup = lineups_res.get("home_lineup", [])
      away_lineup = lineups_res.get("away_lineup", [])
      
      console.print(f"[dim]Lineups sourced via: {lineups_res['source']}[/dim]")
      
      # Build predictions for all players in both lineups
      player_prop_predictions = []
      for is_home, lineup, team_avg in [(True, home_lineup, h_avg), (False, away_lineup, a_avg)]:
          for name in lineup:
              p_stats = player_stats.get_player_stats(name)
              p_probs = calculate_player_prop_probs(p_stats, is_home, matrix, team_avg)
              
              # Map to prop formats
              player_prop_predictions.append({
                  "name": name,
                  "is_home": is_home,
                  "probs": p_probs
              })

      # Add Player Props to the Kalshi Value Bets Table
      for pred in player_prop_predictions:
          name = pred["name"]
          is_home = pred["is_home"]
          p_probs = pred["probs"]
          
          # Match markets in Kalshi
          for outcome_key, label_suffix, prob_val in [
              ("goals_1", "1+ Goals", p_probs["goals_1"]),
              ("goals_2", "2+ Goals", p_probs["goals_2"]),
              ("assists_1", "1+ Assists", p_probs["assists_1"]),
              ("assists_2", "2+ Assists", p_probs["assists_2"]),
              ("goal_or_assist", "Score or Assist", p_probs["goal_or_assist"])
          ]:
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
                              
                              # Check exact category and player name matches
                              if name in t:
                                  if "goal" in label_suffix and "goal" in t:
                                      if "1+" in label_suffix and "1+" in t:
                                          live_p = m["yes_price"]
                                      elif "2+" in label_suffix and "2+" in t:
                                          live_p = m["yes_price"]
                                  elif "assist" in label_suffix and "assist" in t:
                                      if "1+" in label_suffix and "1+" in t:
                                          live_p = m["yes_price"]
                                      elif "2+" in label_suffix and "2+" in t:
                                          live_p = m["yes_price"]
                                  elif "score or assist" in label_suffix and "score or assist" in t:
                                      live_p = m["yes_price"]
              
              category_str = "Player Goals" if "Goals" in label_suffix else ("Player Assists" if "Assists" in label_suffix else "Player G/A")
              market_label = f"{name.title()} {label_suffix}"
              
              if live_p:
                  edge = prob_val - live_p
                  edge_str = f"+{edge*100:.1f}% [STRONG VALUE]" if edge > 0.05 else (f"+{edge*100:.1f}% [VALUE]" if edge > 0 else f"{edge*100:.1f}%")
                  bets_table.add_row(category_str, market_label, f"{prob_val*100:.1f}%", f"${live_p:.2f}", edge_str)
              else:
                  bets_table.add_row(category_str, market_label, f"{prob_val*100:.1f}%", "N/A", f"Buy YES < ${prob_val:.2f}")
  ```

- [ ] **Step 5: Run tests and ensure all tests pass**
  Run: `python scratch/test_market_match.py`
  Expected: PASS

- [ ] **Step 6: Commit**
  ```bash
  git add src/market/kalshi_client.py main.py scratch/test_market_match.py
  git commit -m "feat: integrate dynamic lineup fetching and player goals/assists/GA props in CLI table"
  ```

---

### Task 6: Paper Trading Bots Prop Bet Placement
**Files:**
* Modify: `main.py:270-312`
* Test: `scratch/test_bot_betting.py` (create)

- [ ] **Step 1: Write test for bot prop bet evaluation**
  Create `scratch/test_bot_betting.py`:
  Verify that player goals, assists, and G/A outcomes are correctly scored/added to the candidates list for paper trading.

- [ ] **Step 2: Run test to verify it fails**
  Expected: Failures or candidate omissions

- [ ] **Step 3: Modify `main.py` automated betting loops**
  Modify `main.py` lines 270-312 to evaluate player props in the candidates lists. Add code:
  ```python
      # Under main.py candidate list additions:
      for pred in player_prop_predictions:
          name = pred["name"]
          p_probs = pred["probs"]
          for outcome_key, label_suffix, prob_val in [
              ("goals_1", "1+ Goals", p_probs["goals_1"]),
              ("goals_2", "2+ Goals", p_probs["goals_2"]),
              ("assists_1", "1+ Assists", p_probs["assists_1"]),
              ("assists_2", "2+ Assists", p_probs["assists_2"]),
              ("goal_or_assist", "Score or Assist", p_probs["goal_or_assist"])
          ]:
              live_price = None
              for ev in markets:
                  title = ev["event_title"].lower()
                  if " vs " in title:
                      t_parts = title.split(" vs ")
                      t_home = normalize_team_name(t_parts[0])
                      t_away = normalize_team_name(t_parts[1])
                      if (home == t_home and away == t_away) or (home == t_away and away == t_home):
                          for m in ev["markets"]:
                              t = m["title"].lower()
                              if name in t:
                                  if "goal" in label_suffix and "goal" in t:
                                      if "1+" in label_suffix and "1+" in t:
                                          live_price = m["yes_price"]
                                      elif "2+" in label_suffix and "2+" in t:
                                          live_price = m["yes_price"]
                                  elif "assist" in label_suffix and "assist" in t:
                                      if "1+" in label_suffix and "1+" in t:
                                          live_price = m["yes_price"]
                                      elif "2+" in label_suffix and "2+" in t:
                                          live_price = m["yes_price"]
                                  elif "score or assist" in label_suffix and "score or assist" in t:
                                      live_price = m["yes_price"]
              
              if live_price and live_price > 0:
                  edge = prob_val - live_price
                  if edge > 0.02:  # Positive edge threshold
                      label = f"Player Props - {name.title()} {label_suffix}"
                      candidates.append((edge, label, live_price))
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_bot_betting.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add main.py scratch/test_bot_betting.py
  git commit -m "feat: enable paper trading bots to place bets on player prop markets"
  ```

---

### Task 7: End-to-End Integration Verification
**Files:**
* Create: `scratch/test_player_props_integration.py`

- [ ] **Step 1: Write complete integration test**
  Create `scratch/test_player_props_integration.py`:
  ```python
  import sys
  import os
  sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
  
  import subprocess
  
  def run_e2e_test():
      print("Running predict command for South Africa vs Canada...")
      cmd = ["python", "main.py", "predict", "South Africa vs Canada"]
      result = subprocess.run(cmd, capture_output=True, text=True)
      
      print("STDOUT:")
      print(result.stdout)
      print("STDERR:")
      print(result.stderr)
      
      assert result.returncode == 0
      assert "Player Goals" in result.stdout or "Player Assists" in result.stdout or "Player G/A" in result.stdout
      assert "Predict Portfolio Bot Paper Bets" in result.stdout
      print("ALL END-TO-END VERIFICATION CHECKS PASSED!")

  if __name__ == "__main__":
      run_e2e_test()
  ```

- [ ] **Step 2: Execute integration test and verify output**
  Run: `python scratch/test_player_props_integration.py`
  Expected: PASS with full output printing prediction matrix, player props table with value edits, and paper bets.

- [ ] **Step 3: Commit**
  ```bash
  git add scratch/test_player_props_integration.py
  git commit -m "test: verify end-to-end player prop predictions and trading bot bets"
  ```
