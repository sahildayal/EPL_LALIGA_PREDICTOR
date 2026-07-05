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
