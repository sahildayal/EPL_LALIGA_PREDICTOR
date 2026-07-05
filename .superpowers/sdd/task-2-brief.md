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

