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

