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

