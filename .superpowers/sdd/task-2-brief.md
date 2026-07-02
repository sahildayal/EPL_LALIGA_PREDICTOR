### Task 2: Probability Modeling & Poisson CDF

**Files:**
- Modify: `src/parlay/parlay_engine.py`
- Test: `scratch/test_parlay_engine_corners.py`

**Interfaces:**
- Consumes: `src.data.scrapers.corners.get_team_recent_corners`
- Produces: `get_corners_probability(home: str, away: str, line: float) -> float`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_parlay_engine_corners.py`:
  ```python
  import unittest
  from unittest.mock import patch
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestParlayEngineCorners(unittest.TestCase):
      @patch("src.parlay.parlay_engine.get_team_recent_corners")
      def test_corner_probabilities(self, mock_corners):
          # Mock home team (6 won, 4 conceded) and away team (5 won, 5 conceded)
          mock_corners.side_effect = lambda t: {"won": 6.0, "conceded": 4.0} if t == "brazil" else {"won": 5.0, "conceded": 5.0}
          
          from src.models.statistical import DixonColesModel
          from src.parlay.parlay_engine import ParlayEngine
          
          dc = DixonColesModel()
          engine = ParlayEngine(dc)
          
          # Expected total corners won = 6 + 5 = 11
          # Check probability over 8.5 corners
          p_over = engine.get_corners_probability("brazil", "japan", 8.5)
          self.assertTrue(0.0 <= p_over <= 1.0)
          self.assertTrue(p_over > 0.5)

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_parlay_engine_corners.py`
  Expected: FAIL with `AttributeError` on `get_corners_probability`

- [ ] **Step 3: Implement Poisson expectation and probability**
  Add the method to `ParlayEngine` in `src/parlay/parlay_engine.py`:
  ```python
      def get_corners_probability(self, home: str, away: str, line: float) -> float:
          """
          Calculates probability of total corners exceeding 'line' using Poisson CDF.
          """
          from src.data.scrapers.corners import get_team_recent_corners
          h_stats = get_team_recent_corners(home)
          a_stats = get_team_recent_corners(away)
          
          # Calculate expected lambda for both sides
          # Baseline tournament corners conceded is 4.8
          lambda_h = h_stats["won"] * (a_stats["conceded"] / 4.8)
          lambda_a = a_stats["won"] * (h_stats["conceded"] / 4.8)
          
          lambda_total = lambda_h + lambda_a
          if lambda_total <= 0:
              lambda_total = 9.6 # fallback default

          # Poisson CDF: P(X <= k) = sum_{i=0}^k e^{-lambda} * lambda^i / i!
          k = int(line)
          cdf = 0.0
          for i in range(k + 1):
              cdf += math.exp(-lambda_total) * (lambda_total ** i) / math.factorial(i)
              
          p_over = 1.0 - cdf
          return round(max(0.0, min(1.0, p_over)), 4)
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_parlay_engine_corners.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/parlay/parlay_engine.py scratch/test_parlay_engine_corners.py
  git commit -m "feat: implement corner expectation Poisson modeling and get_corners_probability"
  ```

---
