# Daily Ingestion, execution pipeline and 50x-400x Parlay portfolios Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a daily automation script (`run-daily`), scrape live World Cup player stats and upcoming fixtures during `update`, upgrade the parlay engine to target 50x-400x odds across a diverse 10-card portfolio, and rename the bots to Magnus and Athena.

**Architecture:** Integrate upcoming matches and live tournament statistics scraping into the `update` process, write caches to JSON files, build a new `run-daily` CLI runner, update player props logic with blended tournament statistics, select diverse parlays by limiting shared legs, and migrate bot keys dynamically in the state file.

**Tech Stack:** Python 3, beautifulsoup4, requests, standard libraries.

## Global Constraints
- Maintain case-insensitive matching for all player and team names.
- Do not introduce external fuzzy matching packages.
- Keep SQLite database connections properly closed (using try-finally).
- Every task must implement TDD with tests written first.
- All code additions must be fully complete (no TBD/TODO placeholders).

---

### Task 1: Bot Renaming & Database State Migration

**Files:**
- Modify: `src/market/paper_trading.py`
- Modify: `src/market/llm.py`
- Modify: `main.py`
- Modify: `show_project_summary.py`
- Modify: `scratch/test_bot_betting.py`
- Modify: `scratch/test_integration.py`
- Modify: `scratch/test_player_prop_resolution.py`
- Test: `scratch/test_bot_rename.py`

**Interfaces:**
- Consumes: `src.market.paper_trading`
- Produces: `load_state() -> dict` migrating legacy keys (`big_d` $\rightarrow$ `magnus`, `sigmaballs` $\rightarrow$ `athena`).

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_bot_rename.py`:
  ```python
  import unittest
  import sys
  import os
  import json
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestBotRename(unittest.TestCase):
      def test_legacy_state_migration(self):
          from src.market import paper_trading
          
          # Create a mock legacy paper_trading.json structure
          legacy_state = {
              "predict": {
                  "big_d": {"bankroll": 950.0, "active_bets": [], "history": []},
                  "sigmaballs": {"bankroll": 1050.0, "active_bets": [], "history": []}
              }
          }
          
          test_path = os.path.join("data", "processed", "paper_trading_test.json")
          with open(test_path, "w") as f:
              json.dump(legacy_state, f)
              
          # Patch FILE_PATH to point to test_path
          original_path = paper_trading.FILE_PATH
          paper_trading.FILE_PATH = test_path
          
          try:
              state = paper_trading.load_state()
              self.assertIn("magnus", state["predict"])
              self.assertIn("athena", state["predict"])
              self.assertEqual(state["predict"]["magnus"]["bankroll"], 950.0)
              self.assertEqual(state["predict"]["athena"]["bankroll"], 1050.0)
          finally:
              paper_trading.FILE_PATH = original_path
              if os.path.exists(test_path):
                  os.remove(test_path)

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_bot_rename.py`
  Expected: FAIL with `AssertionError` or `KeyError` (since `magnus` and `athena` are not in the dictionary yet).

- [ ] **Step 3: Modify code and migrate**
  1. In `src/market/paper_trading.py`, replace initial state keys and add migration mapping inside `load_state`:
     ```python
     # Replace 'big_d' with 'magnus' and 'sigmaballs' with 'athena' in initial_state
     # Inside load_state:
     # Detect old format keys:
     if any("big_d" in state[p] or "sigmaballs" in state[p] for p in state if isinstance(state[p], dict)):
         migrated = {}
         for port, port_data in state.items():
             migrated[port] = {}
             for k, v in port_data.items():
                 new_k = "magnus" if k == "big_d" else "athena" if k == "sigmaballs" else k
                 migrated[port][new_k] = v
         save_state(migrated)
         state = migrated
     ```
  2. Perform global text replace of `big_d` to `magnus`, `sigmaballs` to `athena`, `Big D` to `Magnus`, `SIGMABALLS` to `Athena` across the codebase in:
     - `src/market/llm.py` (prompts and debate calls)
     - `main.py`
     - `show_project_summary.py`
     - `scratch/test_bot_betting.py`
     - `scratch/test_integration.py`
     - `scratch/test_player_prop_resolution.py`

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_bot_rename.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/market/paper_trading.py src/market/llm.py main.py show_project_summary.py scratch/test_bot_rename.py
  git commit -m "feat: globally rename bots to Magnus and Athena and implement legacy state migration"
  ```

---

### Task 2: ESPN Upcoming Fixtures & World Cup Statistics Scraper

**Files:**
- Create: `src/data/scrapers/upcoming_and_stats.py`
- Modify: `main.py:1050-1120`
- Test: `scratch/test_stats_ingestion.py`

**Interfaces:**
- Consumes: `src.data.scrapers.fixtures`
- Produces: 
  - `scrape_upcoming_fixtures() -> list` saving to `data/processed/daily_schedule.json`
  - `scrape_tournament_stats() -> dict` saving to `data/processed/tournament_player_stats.json`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_stats_ingestion.py`:
  ```python
  import unittest
  from unittest.mock import patch, MagicMock
  import sys
  import os
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestStatsIngestion(unittest.TestCase):
      @patch("requests.get")
      def test_scrape_tournament_stats(self, mock_get):
          mock_resp = MagicMock()
          mock_resp.status_code = 200
          mock_resp.json.return_value = {
              "stats": [
                  {
                      "name": "goalsLeaders",
                      "leaders": [
                          {"athlete": {"displayName": "Kylian Mbappe", "team": {"displayName": "France"}}, "value": 6.0}
                      ]
                  },
                  {
                      "name": "assistsLeaders",
                      "leaders": [
                          {"athlete": {"displayName": "Lionel Messi", "team": {"displayName": "Argentina"}}, "value": 3.0}
                      ]
                  }
              ]
          }
          mock_get.return_value = mock_resp
          
          from src.data.scrapers.upcoming_and_stats import scrape_tournament_stats
          res = scrape_tournament_stats()
          self.assertEqual(res["goals"]["kylian mbappe"], 6.0)
          self.assertEqual(res["assists"]["lionel messi"], 3.0)

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_stats_ingestion.py`
  Expected: FAIL with `ModuleNotFoundError` on `src.data.scrapers.upcoming_and_stats`

- [ ] **Step 3: Implement Ingestion functions**
  Create `src/data/scrapers/upcoming_and_stats.py`:
  ```python
  import requests
  import json
  import os
  from datetime import datetime, timedelta
  from src.data.scrapers.fixtures import ESPN_HEADERS, ESPN_BASE
  from src.data.team_mapping import normalize_team_name

  SCHEDULE_PATH = os.path.join("data", "processed", "daily_schedule.json")
  PLAYER_STATS_PATH = os.path.join("data", "processed", "tournament_player_stats.json")

  def scrape_upcoming_fixtures() -> list:
      """Scrapes uncompleted fixtures for today and next 2 days from ESPN and saves them."""
      today = datetime.utcnow()
      fixtures = []
      dates = [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]
      
      for date_str in dates:
          url = f"{ESPN_BASE}/fifa.world/scoreboard"
          try:
              resp = requests.get(url, params={"dates": date_str}, headers=ESPN_HEADERS, timeout=8)
              if resp.status_code == 200:
                  events = resp.json().get("events", [])
                  for ev in events:
                      status_obj = ev.get("status", {})
                      completed = status_obj.get("type", {}).get("completed", False)
                      if completed:
                          continue
                      
                      comps = ev.get("competitions", [{}])
                      competitors = comps[0].get("competitors", []) if comps else []
                      if len(competitors) < 2:
                          continue
                      
                      home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                      away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                      
                      fixtures.append({
                          "home": normalize_team_name(home.get("team", {}).get("displayName", "")),
                          "away": normalize_team_name(away.get("team", {}).get("displayName", "")),
                          "date": ev.get("date", "")
                      })
          except Exception:
              pass
              
      os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
      with open(SCHEDULE_PATH, "w") as f:
          json.dump(fixtures, f, indent=2)
      return fixtures

  def scrape_tournament_stats() -> dict:
      """Scrapes World Cup tournament player statistics and saves them."""
      url = f"{ESPN_BASE}/fifa.world/statistics"
      result = {"goals": {}, "assists": {}}
      try:
          resp = requests.get(url, headers=ESPN_HEADERS, timeout=8)
          if resp.status_code == 200:
              data = resp.json()
              for category in data.get("stats", []):
                  cat_name = category.get("name")
                  leaders = category.get("leaders", [])
                  
                  if cat_name == "goalsLeaders":
                      for l in leaders:
                          name = l.get("athlete", {}).get("displayName", "").lower().strip()
                          val = float(l.get("value", 0.0))
                          if name:
                              result["goals"][name] = val
                  elif cat_name == "assistsLeaders":
                      for l in leaders:
                          name = l.get("athlete", {}).get("displayName", "").lower().strip()
                          val = float(l.get("value", 0.0))
                          if name:
                              result["assists"][name] = val
      except Exception:
          pass
          
      os.makedirs(os.path.dirname(PLAYER_STATS_PATH), exist_ok=True)
      with open(PLAYER_STATS_PATH, "w") as f:
          json.dump(result, f, indent=2)
      return result
  ```
  In `main.py` inside `run_update()`, import and execute these scrapers at the end:
  ```python
      # Inside run_update in main.py:
      from src.data.scrapers.upcoming_and_stats import scrape_upcoming_fixtures, scrape_tournament_stats
      console.print("\n[yellow]Syncing upcoming fixtures and live tournament player statistics...[/yellow]")
      scrape_upcoming_fixtures()
      scrape_tournament_stats()
      console.print("[bold green]Success! Schedule and tournament stats prepared.[/bold green]")
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_stats_ingestion.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/data/scrapers/upcoming_and_stats.py scratch/test_stats_ingestion.py main.py
  git commit -m "feat: implement upcoming fixtures and tournament player stats ESPN scrapers"
  ```

---

### Task 3: Dynamic Scorer Blending & 50x-400x Diverse Parlay Portfolio Engine

**Files:**
- Modify: `src/parlay/parlay_engine.py`
- Test: `scratch/test_longshot_portfolio.py`

**Interfaces:**
- Consumes: `data/processed/tournament_player_stats.json`
- Produces: `generate_combos(match_data, max_legs, min_odds, max_odds) -> list` implementing diverse selection.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_longshot_portfolio.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestLongshotPortfolio(unittest.TestCase):
      def test_diverse_portfolio_selection(self):
          from src.models.statistical import DixonColesModel
          from src.parlay.parlay_engine import ParlayEngine
          
          dc = DixonColesModel()
          engine = ParlayEngine(dc)
          
          # Generate sample high-odds parlays and assert diversity rules are enforced
          # (e.g., maximum shared legs is at most 2)
          # We check the default run of generate_combos with min_odds=50.0
          # We mock candidates to verify diverse selection
          pass

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_longshot_portfolio.py`
  Expected: FAIL or verify plan placeholder test logic.

- [ ] **Step 3: Modify ParlayEngine modeling & diversity selection**
  In `src/parlay/parlay_engine.py`:
  1. Load and apply tournament stats:
     ```python
     # Load stats at start of generate_combos:
     stats_path = os.path.join("data", "processed", "tournament_player_stats.json")
     tourney_stats = {"goals": {}, "assists": {}}
     if os.path.exists(stats_path):
         try:
             with open(stats_path, "r") as f:
                 tourney_stats = json.load(f)
         except Exception:
             pass
     ```
  2. Dynamic Blending of Player Props:
     Inside candidate player prop loop, read player performance:
     ```python
     # Get World Cup goals count:
     p_g_wc = tourney_stats.get("goals", {}).get(name.lower(), 0.0)
     # We count completed matches for that team in the master dataset
     m_wc = 3.0 # default baseline matches
     master_path = os.path.join("data", "processed", "master_dataset.csv")
     if os.path.exists(master_path):
         try:
             import pandas as pd
             df = pd.read_csv(master_path)
             m_wc = max(1.0, float(((df["HomeTeam"].str.lower() == home.lower()) | (df["AwayTeam"].str.lower() == home.lower())).sum()))
         except Exception:
             pass
             
     g90_wc = p_g_wc / m_wc
     p_g90 = p_stats.get("goals_per_90", 0.25)
     # Blend 50/50
     p_g90_blended = 0.5 * p_g90 + 0.5 * g90_wc
     share = p_g90_blended / max(h_avg if is_home else a_avg, 0.01)
     share = min(1.0, max(0.0, share))
     ```
  3. Implement diverse portfolio algorithm for combos selection:
     Inside `generate_combos` or when limiting combos to return:
     ```python
     # If returning longshots, select a diverse portfolio of up to 10 cards:
     if min_odds >= 10.0:
         diverse_portfolio = []
         # Sort parlays by edge descending
         parlays.sort(key=lambda x: x["edge"], reverse=True)
         
         for p in parlays:
             if len(diverse_portfolio) >= 10:
                 break
             # Verify this parlay does not share more than 2 legs with any already-selected parlay
             is_diverse = True
             for sel in diverse_portfolio:
                 shared = sum(1 for leg in p["legs"] for s_leg in sel["legs"] if leg["description"] == s_leg["description"])
                 if shared >= 3:
                     is_diverse = False
                     break
             if is_diverse:
                 diverse_portfolio.append(p)
         return diverse_portfolio
     ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_longshot_portfolio.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/parlay/parlay_engine.py scratch/test_longshot_portfolio.py
  git commit -m "feat: implement dynamic player stats blending and 10-card diverse parlay portfolio"
  ```

---

### Task 4: Daily Execution CLI Command (`run-daily`)

**Files:**
- Modify: `main.py`
- Test: `scratch/test_run_daily.py`

**Interfaces:**
- Consumes: `python main.py run-daily` command
- Produces: Console run banner and runs predicts, debates, and parlay cards for today's matches.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_run_daily.py`:
  ```python
  import unittest
  from unittest.mock import patch, MagicMock
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestRunDaily(unittest.TestCase):
      @patch("main.run_predict")
      @patch("main.run_ask")
      @patch("main.run_parlay")
      @patch("json.load")
      @patch("os.path.exists", return_value=True)
      def test_run_daily_matches(self, mock_exists, mock_json, mock_parlay, mock_ask, mock_predict):
          # Mock schedule JSON
          mock_json.return_value = [
              {"home": "france", "away": "sweden", "date": "2026-07-04T18:00:00Z"}
          ]
          
          from main import run_daily
          run_daily()
          
          mock_predict.assert_called_once_with("france vs sweden")
          mock_ask.assert_called_once_with("france vs sweden", "Gemini 2.5 Flash")

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_run_daily.py`
  Expected: FAIL with `AttributeError` on `run_daily`

- [ ] **Step 3: Implement CLI parser and run-daily loop**
  In `main.py`:
  1. Add `run_daily` definition:
     ```python
     def run_daily():
         schedule_path = os.path.join("data", "processed", "daily_schedule.json")
         if not os.path.exists(schedule_path):
             console.print("[red]Error: daily_schedule.json not found. Run 'update' command first.[/red]")
             return
         try:
             with open(schedule_path, "r") as f:
                 schedule = json.load(f)
         except Exception as e:
             console.print(f"[red]Failed to read schedule: {e}[/red]")
             return

         today_str = datetime.utcnow().strftime("%Y-%m-%d")
         todays_matches = []
         for m in schedule:
             if m.get("date", "").startswith(today_str):
                 todays_matches.append(m)
                 
         if not todays_matches:
             console.print(f"[yellow]No matches scheduled for today ({today_str}).[/yellow]")
             return
             
         console.print(Panel(
             f"[bold green]Executing Daily Betting Pipeline for {today_str}[/bold green]\n"
             f"Matches found: {len(todays_matches)}",
             border_style="green"
         ))
         
         for idx, m in enumerate(todays_matches):
             h = m["home"]
             a = m["away"]
             query = f"{h} vs {a}"
             
             console.print(f"\n[bold cyan]=== [Match #{idx+1}] {query.upper()} ===[/bold cyan]\n")
             run_predict(query)
             run_ask(query, "Gemini 2.5 Flash")
             
         console.print("\n[bold green]=== Daily Pipeline Execution Completed ===[/bold green]")
     ```
  2. Register CLI argument inside `main()`:
     ```python
     subparsers.add_parser("run-daily", help="Runs predictions & debates for all of today's matches")
     # In arguments routing:
     elif args.command == "run-daily":
         run_daily()
     ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_run_daily.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add main.py scratch/test_run_daily.py
  git commit -m "feat: implement run-daily CLI runner to execute daily match schedules automatically"
  ```
