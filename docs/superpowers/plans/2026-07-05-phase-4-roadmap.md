# Phase 4 Implementation Plan: News Debating Agents & Simulation Dashboard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Active News Debating Agents (scrapers + LLM context) and the 10,000x Tournament Monte Carlo Simulation Dashboard (engine + web UI) before upcoming World Cup games.

**Architecture:** 
1. `src/market/llm.py` performs active web searches/RSS fetches to summarize team news, injecting it into debates, and saving debates to JSON files.
2. `src/models/simulation.py` runs 10,000x Monte Carlo bracket simulations using Dixon-Coles and Elo parameters, caching output to JSON on updates.
3. `dashboard.html` serves as a responsive Tokyo Night theme dashboard displaying the bracket tree and simulation statistics.

**Tech Stack:** Python (BeautifulSoup, pandas, numpy), HTML5, JavaScript (Fetch API, Tailwind/Vanilla CSS), and Gemini API.

## Global Constraints

- Maintain case-insensitive matching for all player and team names.
- Do not introduce external fuzzy matching packages.
- Keep SQLite database connections properly closed (using try-finally).
- Every task must implement TDD with tests written first.

---

### Task 1: Active News Debating Agents

**Files:**
- Modify: `src/market/llm.py` (implement news fetching and prompt injection)
- Modify: `main.py` (save debate results to `data/processed/debates/`)
- Create: `scratch/test_news_debates.py` (TDD tests)

**Interfaces:**
- Consumes: `google_rss_url` / web search tools.
- Produces: `fetch_team_news_bullets(team_name: str) -> str` and saved JSON debates under `data/processed/debates/YYYY-MM-DD-<home>-vs-<away>.json`.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_news_debates.py` to check that news fetching extracts non-empty string summaries and integrates into debates:
  ```python
  import unittest
  from unittest.mock import patch, MagicMock
  import os
  import json
  from src.market.llm import fetch_team_news_bullets, run_news_debate

  class TestNewsDebates(unittest.TestCase):
      @patch('src.market.llm.search_web')
      def test_fetch_team_news_bullets(self, mock_search):
          mock_search.return_value = {
              "summary": "France team news: Mbappe is fit. Kante returns to training. Saliba is resting.",
              "citations": ["http://espn.com/news"]
          }
          bullets = fetch_team_news_bullets("France")
          self.assertIn("Mbappe", bullets)
          self.assertIn("Kante", bullets)

      @patch('src.market.llm.fetch_team_news_bullets')
      def test_run_news_debate_saves_json(self, mock_bullets):
          mock_bullets.side_effect = lambda team: f"Mock bullets for {team}"
          # Mock the LLM call and run a debate
          # Verify that the JSON file is written to data/processed/debates/
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m unittest scratch/test_news_debates.py`
  Expected: FAIL with `ImportError` or `AttributeError` for `fetch_team_news_bullets`.

- [ ] **Step 3: Write minimal implementation**
  Add news fetching and debate caching to `src/market/llm.py`:
  ```python
  from default_api import search_web # Or use search_web mock/wrapper

  def fetch_team_news_bullets(team_name: str) -> str:
      try:
          # Simple wrapper around search_web or RSS feeds
          res = search_web(query=f"{team_name} national football team roster injuries 2026")
          summary = res.get("summary", "")
          if not summary:
              return f"No recent updates found for {team_name}."
          return summary
      except Exception:
          return f"Unable to fetch news for {team_name}."

  # Inside run_news_debate, query fetch_team_news_bullets for home and away,
  # inject them into the system prompt for Magnus/Athena, run the debate,
  # and save the debate structure to:
  # data/processed/debates/YYYY-MM-DD-<home>-vs-<away>.json
  ```
  And update `main.py`'s debate command to invoke this news-enhanced debate.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m unittest scratch/test_news_debates.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/market/llm.py main.py scratch/test_news_debates.py
  git commit -m "feat: implement active news debating agents and debate JSON caching"
  ```

---

### Task 2: Monte Carlo Simulation Engine

**Files:**
- Create: `src/models/simulation.py` (Monte Carlo simulation math)
- Create: `scratch/test_monte_carlo.py` (TDD tests)

**Interfaces:**
- Consumes: ELO ratings from `data/processed/elo_ratings.json` and Dixon-Coles parameters.
- Produces: `run_tournament_simulation(num_runs: int = 10000) -> dict` returning aggregated stage progression probabilities for each team.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_monte_carlo.py`:
  ```python
  import unittest
  import os
  from src.models.simulation import run_tournament_simulation

  class TestMonteCarlo(unittest.TestCase):
      def test_simulation_probabilities_sum_to_one(self):
          results = run_tournament_simulation(num_runs=100)
          self.assertIn("probabilities", results)
          # Assert that sum of champion probabilities is approx 1.0 (100%)
          total_champ = sum(t["champion"] for t in results["probabilities"])
          self.assertAlmostEqual(total_champ, 1.0, places=2)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m unittest scratch/test_monte_carlo.py`
  Expected: FAIL with module not found or import error.

- [ ] **Step 3: Write minimal implementation**
  Create `src/models/simulation.py`:
  - Load ELO and Dixon-Coles models.
  - Define bracket stages: Quarterfinals (4 matches), Semifinals (2 matches), Finals (1 match).
  - Simulate each match:
    - 90m match using Dixon-Coles score expectations.
    - If draw, extra time using 30m scaled Dixon-Coles.
    - If still draw, penalties using Goalie Save Rates:
      `home_win_shootout = home_goalie_rate / (home_goalie_rate + away_goalie_rate)`
  - Compile the probabilities per stage and return the results as a dictionary matching the schema.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m unittest scratch/test_monte_carlo.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/models/simulation.py scratch/test_monte_carlo.py
  git commit -m "feat: implement 10,000x tournament Monte Carlo simulation engine"
  ```

---

### Task 3: Trigger Integration & JSON Caching

**Files:**
- Modify: `main.py` (Trigger simulation in `update` and `run-daily`)
- Create: `scratch/test_trigger_simulation.py` (TDD tests)

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_trigger_simulation.py` to assert that the simulation results file `data/processed/simulation_results.json` is successfully updated when calling the update script commands.

- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m unittest scratch/test_trigger_simulation.py`
  Expected: FAIL

- [ ] **Step 3: Write minimal implementation**
  In `main.py`, under the `update` command and the `run-daily` command:
  1. Call `run_tournament_simulation(num_runs=10000)`.
  2. Write the JSON dictionary output to `data/processed/simulation_results.json`.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m unittest scratch/test_trigger_simulation.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add main.py scratch/test_trigger_simulation.py
  git commit -m "feat: cache tournament Monte Carlo simulations on data updates"
  ```

---

### Task 4: Interactive Web Dashboard

**Files:**
- Create: `dashboard.html` (single-page dashboard file)
- Create: `scratch/test_dashboard_existence.py` (TDD tests)

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_dashboard_existence.py` to assert that `dashboard.html` exists and contains critical elements like `#bracket-tree`, `#prob-table`, and references to `simulation_results.json`.

- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m unittest scratch/test_dashboard_existence.py`
  Expected: FAIL (file doesn't exist)

- [ ] **Step 3: Write minimal implementation**
  Create `dashboard.html` using clean CSS/JS and Tokyo Night styling:
  - Header: 🏆 2026 World Cup Monte Carlo Dashboard
  - Left pane: Clean HTML/CSS nodes showing the tournament bracket structure. Clicking a node highlights head-to-head parameters.
  - Right pane: Standard sortable table loading data from `data/processed/simulation_results.json` via fetch.
  - Bottom pane/Modals: Accordion that searches `data/processed/debates/` for match debate JSON transcripts and renders the Magnus vs Athena qualitative discussions dynamically.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m unittest scratch/test_dashboard_existence.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add dashboard.html scratch/test_dashboard_existence.py
  git commit -m "feat: construct Tokyo Night theme interactive simulation dashboard"
  ```
