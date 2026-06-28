import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from sklearn.neural_network import MLPClassifier

from src.models.base import BaseModel

MODELS_DIR = Path(__file__).parent.parent.parent / "data" / "models"


class StackingEnsembleModel(BaseModel):
    def __init__(self):
        super().__init__("StackingEnsemble")
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
                random_state=42,
                verbose=-1
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
            final_estimator=make_pipeline(StandardScaler(), LogisticRegression(penalty='l2', C=1.0)),
            cv=3,
            n_jobs=-1,
            passthrough=False
        )

    def train(self, X: np.ndarray, y: np.ndarray):
        """Train the stacking ensemble model."""
        self.clf.fit(X, y)
        self.is_fitted = True

    def fit(self, X: np.ndarray, y: np.ndarray):
        """Fit alias to match Scikit-Learn style interface and tests."""
        self.train(X, y)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probabilities for classes: [Home Win, Draw, Away Win]."""
        if not self.is_fitted:
            X_2d = X.reshape(1, -1) if X.ndim == 1 else X
            return np.tile([0.38, 0.28, 0.34], (len(X_2d), 1))
        X_2d = X.reshape(1, -1) if X.ndim == 1 else X
        return self.clf.predict_proba(X_2d)

    def save(self):
        """Save the fitted stacking classifier to disk."""
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, MODELS_DIR / "stacking_clf.pkl")

    def load(self) -> bool:
        """Load the stacked classifier model from disk."""
        try:
            self.clf = joblib.load(MODELS_DIR / "stacking_clf.pkl")
            self.is_fitted = True
            return True
        except Exception:
            return False
