### Task 5: Two-Stage Stacking Classifier ML Ensemble

**Files:**
- Create: `src/models/stacking_ensemble.py`
- Test: `scratch/test_stacking_ensemble.py`

**Interfaces:**
- Consumes: Tabular training features
- Produces: `StackingEnsembleModel`, `StackingEnsembleModel.fit(X, y)`, `StackingEnsembleModel.predict_proba(X)`

- [ ] **Step 1: Write the failing test**
  Create `scratch/test_stacking_ensemble.py` to verify ensembling works:
  ```python
  import unittest
  import numpy as np
  import sys
  from pathlib import Path
  sys.path.append(str(Path(__file__).resolve().parents[1]))
  from src.models.stacking_ensemble import StackingEnsembleModel

  class TestStackingEnsemble(unittest.TestCase):
      def test_ensemble_prediction(self):
          X = np.random.rand(50, 10)
          y = np.random.choice([0, 1, 2], size=50) # 0: Home, 1: Draw, 2: Away
          model = StackingEnsembleModel()
          model.fit(X, y)
          probs = model.predict_proba(X[:2])
          self.assertEqual(probs.shape, (2, 3))
  ```
- [ ] **Step 2: Run test to verify it fails**
  Run: `python scratch/test_stacking_ensemble.py`
  Expected: FAIL with `ModuleNotFoundError`
- [ ] **Step 3: Write minimal implementation**
  Create `src/models/stacking_ensemble.py` wrapping XGBoost, LightGBM, and MLP into a StackingClassifier with Ridge Logistic Regression meta-learner.
  ```python
  from sklearn.ensemble import StackingClassifier
  from sklearn.linear_model import LogisticRegression
  from sklearn.preprocessing import StandardScaler
  from sklearn.pipeline import make_pipeline
  from xgboost import XGBClassifier
  from lightgbm import LGBMClassifier
  from sklearn.neural_network import MLPClassifier

  class StackingEnsembleModel:
      def __init__(self):
          base_estimators = [
              ('xgb', XGBClassifier(
                  n_estimators=100,
                  max_depth=3,
                  learning_rate=0.1,
                  subsample=0.8,
                  random_state=42,
                  eval_metric='mlogloss'
              )),
              ('lgbm', LGBMClassifier(
                  n_estimators=100,
                  max_depth=3,
                  learning_rate=0.1,
                  subsample=0.8,
                  random_state=42
              )),
              ('mlp', make_pipeline(
                  StandardScaler(),
                  MLPClassifier(
                      hidden_layer_sizes=(32, 16),
                      activation='relu',
                      max_iter=300,
                      random_state=42
                  )
              ))
          ]
          self.clf = StackingClassifier(
              estimators=base_estimators,
              final_estimator=LogisticRegression(penalty='l2', C=1.0),
              cv=3,
              n_jobs=-1,
              passthrough=True
          )

      def fit(self, X, y):
          self.clf.fit(X, y)

      def predict_proba(self, X):
          return self.clf.predict_proba(X)
  ```
- [ ] **Step 4: Run test to verify it passes**
  Run: `python scratch/test_stacking_ensemble.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add src/models/stacking_ensemble.py scratch/test_stacking_ensemble.py
  git commit -m "feat: implement StackingEnsembleModel integrating XGBoost, LightGBM, and MLP"
  ```