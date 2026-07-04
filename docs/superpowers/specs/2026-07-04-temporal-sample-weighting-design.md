# Design Spec: Temporal Sample Weighting for Machine Learning Models

**Date:** 2026-07-04  
**Status:** Approved  
**Author:** Antigravity  

---

## 1. Objective
Optimize the machine learning training stack (XGBoost, LightGBM, RandomForest, SVM, Logistic Regression) to prioritize recent football regimes and modern match data over stale historical results. This is achieved by applying an exponential time-decay weight to each match during model training.

---

## 2. Technical Design

### A. Temporal Weight Formula
For each training match $i$:
1. Calculate $t_{\text{years}} = \frac{\text{Current Date} - \text{Match Date}}{365.25}$.
2. Compute the decay weight using a half-life of 4 years ($\lambda = 0.1733$):
   $$w_i = \exp(-0.1733 \times t_{\text{years}})$$
3. Clamp the minimum weight to `0.05` to retain a tiny baseline signal for older games:
   $$w_i = \max(0.05, w_i)$$

### B. Machine Learning Trainer Integration (`src/models/trainer.py`)
- During training dataset preparation, compute the sample weights array `sample_weights`.
- Modify the base learner fitting logic to inspect whether the learner's `fit` method supports `sample_weight`.
- Pass `sample_weight` conditionally:
  ```python
  import inspect
  
  # For each base model in the stack:
  fit_params = inspect.signature(model.fit).parameters
  if "sample_weight" in fit_params:
      model.fit(X, y, sample_weight=sample_weights)
  else:
      model.fit(X, y)
  ```
- This dynamically handles models that do not natively support sample weights (like scikit-learn's `MLPClassifier`) while correctly weighting XGBoost, LightGBM, SVM, RandomForest, and Logistic Regression.

---

## 3. Testing & Verification Plan
- **Unit Test (`scratch/test_temporal_weighting.py`)**:
  - Verify that sample weights are correctly calculated based on match dates.
  - Verify that older matches have significantly lower weights than recent matches.
  - Verify that the models train successfully without throwing exceptions when sample weights are passed.
