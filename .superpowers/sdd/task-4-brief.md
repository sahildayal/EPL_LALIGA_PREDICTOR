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
