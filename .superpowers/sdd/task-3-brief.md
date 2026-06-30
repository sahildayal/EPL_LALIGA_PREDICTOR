### Task 3: Knockout Progression Model (To Qualify)

**Files:**
- Modify: `src/predictor.py`, `src/market/llm.py`, `main.py`
- Test: `scratch/test_progression_model.py`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_progression_model.py`:
  ```python
  import unittest
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  
  class TestProgressionModel(unittest.TestCase):
      def test_advancement_probabilities(self):
          from src.predictor import predict_match
          res = predict_match("brazil", "japan")
          self.assertTrue(hasattr(res, "progression_probabilities"))
          p_h = res.progression_probabilities["home_advances"]
          p_a = res.progression_probabilities["away_advances"]
          self.assertAlmostEqual(p_h + p_a, 1.0, places=4)
          # Brazil (higher Elo) should have higher advance probability
          self.assertTrue(p_h > p_a)
  
  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_progression_model.py`
  Expected: FAIL with `AttributeError` on `progression_probabilities`

- [ ] **Step 3: Implement progression forecasts**
  In `src/predictor.py` inside `PredictionResult`:
  ```python
  class PredictionResult:
      def __init__(self, home: str, away: str, probabilities: dict, model_breakdown: dict, sentiment: float, elo_diff: float, progression_probabilities: dict = None):
          self.home = home
          self.away = away
          self.probabilities = probabilities
          self.model_breakdown = model_breakdown
          self.sentiment = sentiment
          self.elo_diff = elo_diff
          self.progression_probabilities = progression_probabilities or {"home_advances": 0.50, "away_advances": 0.50}
  ```
  In `predict_match`:
  ```python
      # Goalkeeper penalty save rate logic
      # Brazil GK (Alisson): 33%, Japan GK (Zion Suzuki): 25%
      h_gk_rate = 0.33
      a_gk_rate = 0.25
      
      # Probability of home team advancing if it goes to Extra Time/Penalties
      # Adjusted by Elo diff and Goalkeeper penalty-saving rates
      p_et_pens_home = 0.50 + 0.0008 * elo_diff + 0.10 * (h_gk_rate - a_gk_rate)
      p_et_pens_home = max(0.30, min(0.70, p_et_pens_home))
      
      # Combined advances probability
      p_home_advances = blended["home_win"] + blended["draw"] * p_et_pens_home
      p_away_advances = 1.0 - p_home_advances
      
      prog_probs = {
          "home_advances": round(p_home_advances, 4),
          "away_advances": round(p_away_advances, 4)
      }
  ```
  Pass `prog_probs` to `PredictionResult`.
  Update `main.py` `run_predict` to print the progression forecast matrix to console.
  Update the debate prompt in `src/market/llm.py` to inject the new progression probabilities.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_progression_model.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/predictor.py src/market/llm.py main.py scratch/test_progression_model.py
  git commit -m "feat: implement To-Qualify progression model using goalkeeper penalty stats"
  ```

---
