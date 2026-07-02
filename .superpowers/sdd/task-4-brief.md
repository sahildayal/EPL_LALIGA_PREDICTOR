### Task 4: CLI output formatting and Ask prompt update

**Files:**
- Modify: `main.py`
- Test: `scratch/test_cli_integration.py`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_cli_integration.py`:
  ```python
  import unittest
  from unittest.mock import patch, MagicMock
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestCliIntegration(unittest.TestCase):
      @patch("main.predict_match")
      @patch("main.get_team_recent_corners")
      def test_cli_forecast_outputs(self, mock_corners, mock_predict):
          mock_corners.return_value = {"won": 6.0, "conceded": 4.0}
          
          mock_res = MagicMock()
          mock_res.probabilities = {"home_win": 0.50, "draw": 0.20, "away_win": 0.30}
          mock_res.sentiment = 0.0
          mock_res.elo_diff = 0.0
          mock_res.progression_probabilities = {"home_advances": 0.60, "away_advances": 0.40}
          mock_predict.return_value = mock_res
          
          from main import run_predict
          # Verifies executing main prediction runs successfully without syntax exceptions
          try:
              run_predict("brazil vs japan")
              passed = True
          except Exception:
              passed = False
          self.assertTrue(passed)

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_cli_integration.py`
  Expected: FAIL (expected corners table formatting not yet printed or missing imports)

- [ ] **Step 3: Modify main.py display outputs**
  In `main.py` inside `run_predict`:
  Calculate expected corners won, conceded, and total. Print expected corners matrix to console:
  ```python
      # Under ELO ratings print in main.py:
      from src.data.scrapers.corners import get_team_recent_corners
      h_crn = get_team_recent_corners(home)
      a_crn = get_team_recent_corners(away)
      
      lambda_h = h_crn["won"] * (a_crn["conceded"] / 4.8)
      lambda_a = a_crn["won"] * (h_crn["conceded"] / 4.8)
      
      crn_table = Table(title=f"{home.title()} vs {away.title()} Corner Kicks Expectation", box=box.SIMPLE)
      crn_table.add_column("Team", style="cyan")
      crn_table.add_column("Avg Corners Won", style="green")
      crn_table.add_column("Expected Corners (Match)", style="bold green")
      crn_table.add_row(home.title(), f"{h_crn['won']:.1f}", f"{lambda_h:.1f}")
      crn_table.add_row(away.title(), f"{a_crn['won']:.1f}", f"{lambda_a:.1f}")
      crn_table.add_row("Total Expected", "-", f"{lambda_h + lambda_a:.1f}")
      console.print(crn_table)
  ```
  Update the debate prompt in `src/market/llm.py` to accept and inject corners expectations.
  Update `generate_debate` in `src/market/llm.py` to interpolate corners data:
  ```python
  # Under Match Data inside generate_debate:
  - Expected Corner Kicks: {corners_expectation}
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_cli_integration.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add main.py src/market/llm.py scratch/test_cli_integration.py
  git commit -m "feat: integrate corner expectations display in predict and LLM debate prompts"
  ```
