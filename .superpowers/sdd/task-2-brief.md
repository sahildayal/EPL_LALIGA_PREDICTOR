### Task 2: Confederation ELO Calibration

**Files:**
- Modify: `src/predictor.py`
- Test: `scratch/test_confederation_calibration.py`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_confederation_calibration.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  
  class TestConfedCalibration(unittest.TestCase):
      def test_confederation_boosting(self):
          from src.predictor import predict_match
          # Brazil (CONMEBOL) vs Japan (AFC). Check Elo calibration.
          res = predict_match("brazil", "japan")
          # Brazil ELO boost (+50) minus Japan ELO penalty (-20) = 70 rating points shift
          self.assertEqual(res.elo_diff, 232.1) # rating diff (162.1) + confed diff (70.0)
  
  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_confederation_calibration.py`
  Expected: FAIL with `AssertionError: 162.1 != 232.1`

- [ ] **Step 3: Modify predictor code**
  In `src/predictor.py`, add the confederation mappings and ELO boosts:
  ```python
  CONFEDERATION_BOOST = {
      "conmebol": 50.0,
      "uefa": 40.0,
      "caf": 0.0,
      "afc": -20.0,
      "concacaf": -30.0,
      "ofc": -80.0
  }
  
  TEAM_CONFEDERATION = {
      "brazil": "conmebol", "argentina": "conmebol", "uruguay": "conmebol", "colombia": "conmebol", "ecuador": "conmebol", "chile": "conmebol", "paraguay": "conmebol",
      "france": "uefa", "england": "uefa", "spain": "uefa", "portugal": "uefa", "netherlands": "uefa", "germany": "uefa", "italy": "uefa", "croatia": "uefa", "belgium": "uefa", "denmark": "uefa", "switzerland": "uefa", "sweden": "uefa", "norway": "uefa",
      "morocco": "caf", "senegal": "caf", "egypt": "caf", "tunisia": "caf",
      "japan": "afc", "south korea": "afc", "australia": "afc", "saudi arabia": "afc", "iran": "afc", "jordan": "afc",
      "mexico": "concacaf", "usa": "concacaf", "canada": "concacaf", "haiti": "concacaf",
      "new zealand": "ofc"
  }
  ```
  In `predict_match`:
  ```python
      h_conf = TEAM_CONFEDERATION.get(home_lower, "uefa")
      a_conf = TEAM_CONFEDERATION.get(away_lower, "uefa")
      
      h_boost = CONFEDERATION_BOOST.get(h_conf, 0.0)
      a_boost = CONFEDERATION_BOOST.get(a_conf, 0.0)
      
      h_elo = ELO_PREDICTOR.get(home_lower)
      a_elo = ELO_PREDICTOR.get(away_lower)
      
      # Apply boost
      elo_diff = (h_elo + h_boost) - (a_elo + a_boost)
  ```
  Make sure this adjusted ELO rating is also fed into ELO probability prediction inside `predict_match`.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_confederation_calibration.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/predictor.py scratch/test_confederation_calibration.py
  git commit -m "feat: calibrate ELO rating diffs with confederation coefficients"
  ```

---
