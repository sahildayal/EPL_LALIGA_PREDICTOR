# Temporal Sample Weighting for ML Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the ML model training pipeline to calculate and apply exponential time-decay sample weights during fitting, prioritizing modern fixtures.

**Architecture:** Calculate sample weights based on the time elapsed between the match date and the execution date, and pass these weights to base ML classifiers during training.

---

### Task 1: Temporal Weight Calculation & ML Fit Ingestion

**Files:**
- Modify: `src/models/trainer.py`
- Test: `scratch/test_temporal_weighting.py`

**Interfaces:**
- Consumes: `data/processed/master_dataset.csv`
- Produces: Calibrated ML models trained with temporal sample weights.

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_temporal_weighting.py`:
  ```python
  import unittest
  import sys
  import pandas as pd
  import numpy as np
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))

  class TestTemporalWeighting(unittest.TestCase):
      def test_weight_decay_calculation(self):
          from src.models.trainer import calculate_sample_weights
          
          # Match dates: 1 today, 1 four years ago (~1461 days), 1 eight years ago
          dates = pd.to_datetime([
              pd.Timestamp.now(),
              pd.Timestamp.now() - pd.Timedelta(days=1461),
              pd.Timestamp.now() - pd.Timedelta(days=1461 * 2)
          ])
          
          weights = calculate_sample_weights(dates)
          
          self.assertEqual(len(weights), 3)
          self.assertAlmostEqual(weights[0], 1.0, places=2)
          self.assertAlmostEqual(weights[1], 0.5, places=2)
          # Clamped at 0.05
          self.assertAlmostEqual(weights[2], 0.25, places=2)

  if __name__ == '__main__':
      unittest.main()
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_temporal_weighting.py`
  Expected: FAIL with `ModuleNotFoundError` or `ImportError` on `calculate_sample_weights`

- [ ] **Step 3: Implement weights calculation and update training code**
  In `src/models/trainer.py`:
  1. Add `calculate_sample_weights` function:
     ```python
     import numpy as np
     import pandas as pd
     
     def calculate_sample_weights(dates: pd.Series) -> np.ndarray:
         """Calculates exponential time-decay sample weights with a 4-year half-life."""
         current_time = pd.Timestamp.now()
         # Compute years ago
         years_ago = (current_time - pd.to_datetime(dates)).dt.days / 365.25
         # Half life decay lambda = ln(2)/4 = 0.1733
         weights = np.exp(-0.173286 * years_ago)
         # Clamp at 0.05
         return np.maximum(0.05, weights)
     ```
  2. Locate where `model.fit(X, y)` or similar is called.
     Wait, let's view where models are trained. We can check `src/models/trainer.py` to see the structure of model training.
     Let's write a python query to inspect `src/models/trainer.py` or inspect it via `view_file` to find the exact training function.
     Wait! Let's modify the fit calls using signature inspection:
     ```python
     import inspect
     # Inside trainer.py model training loop:
     # Calculate sample weights:
     weights = calculate_sample_weights(df["Date"]) # df is the loaded master dataset
     
     # When fitting each base model:
     fit_params = inspect.signature(model.fit).parameters
     if "sample_weight" in fit_params:
         model.fit(X, y, sample_weight=weights)
     else:
         model.fit(X, y)
     ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_temporal_weighting.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add src/models/trainer.py scratch/test_temporal_weighting.py
  git commit -m "feat: implement temporal sample weighting for ML model training"
  ```
