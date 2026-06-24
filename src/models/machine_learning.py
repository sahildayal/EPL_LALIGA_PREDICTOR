import numpy as np
import joblib
from pathlib import Path
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.svm import SVC, SVR
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.multioutput import MultiOutputRegressor
import xgboost as xgb
from src.models.base import BaseModel

MODELS_DIR = Path(__file__).parent.parent.parent / "data" / "models"


class LogisticRegressionModel(BaseModel):
    def __init__(self):
        super().__init__("LogisticRegression")
        self.clf = LogisticRegression(multi_class="multinomial", solver="lbfgs", class_weight="balanced", max_iter=3000)
        self.reg_h = LinearRegression()
        self.reg_a = LinearRegression()
        self.scaler = StandardScaler()

    def train(self, X: np.ndarray, y_res: np.ndarray, y_goals: np.ndarray = None):
        X_scaled = self.scaler.fit_transform(X)
        self.clf.fit(X_scaled, y_res)
        if y_goals is not None:
            self.reg_h.fit(X_scaled, y_goals[:, 0])
            self.reg_a.fit(X_scaled, y_goals[:, 1])
        self.is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([[0.38, 0.28, 0.34]])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        return self.clf.predict_proba(X_scaled)

    def predict_goals(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([1.3, 1.1])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        h = self.reg_h.predict(X_scaled)
        a = self.reg_a.predict(X_scaled)
        return np.column_stack([h, a])

    def save(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, MODELS_DIR / "lr_clf.pkl")
        joblib.dump(self.reg_h, MODELS_DIR / "lr_reg_h.pkl")
        joblib.dump(self.reg_a, MODELS_DIR / "lr_reg_a.pkl")
        joblib.dump(self.scaler, MODELS_DIR / "lr_scaler.pkl")

    def load(self) -> bool:
        try:
            self.clf = joblib.load(MODELS_DIR / "lr_clf.pkl")
            self.reg_h = joblib.load(MODELS_DIR / "lr_reg_h.pkl")
            self.reg_a = joblib.load(MODELS_DIR / "lr_reg_a.pkl")
            self.scaler = joblib.load(MODELS_DIR / "lr_scaler.pkl")
            self.is_fitted = True
            return True
        except Exception:
            return False


class SVMModel(BaseModel):
    def __init__(self):
        super().__init__("SupportVectorMachine")
        self.clf = SVC(kernel="rbf", C=1.0, gamma="scale", class_weight="balanced", probability=True)
        self.reg_h = SVR(kernel="rbf", C=1.0, gamma="scale")
        self.reg_a = SVR(kernel="rbf", C=1.0, gamma="scale")
        self.scaler = StandardScaler()

    def train(self, X: np.ndarray, y_res: np.ndarray, y_goals: np.ndarray = None):
        X_scaled = self.scaler.fit_transform(X)
        self.clf.fit(X_scaled, y_res)
        if y_goals is not None:
            self.reg_h.fit(X_scaled, y_goals[:, 0])
            self.reg_a.fit(X_scaled, y_goals[:, 1])
        self.is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([[0.38, 0.28, 0.34]])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        return self.clf.predict_proba(X_scaled)

    def predict_goals(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([1.3, 1.1])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        h = self.reg_h.predict(X_scaled)
        a = self.reg_a.predict(X_scaled)
        return np.column_stack([h, a])

    def save(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, MODELS_DIR / "svm_clf.pkl")
        joblib.dump(self.reg_h, MODELS_DIR / "svm_reg_h.pkl")
        joblib.dump(self.reg_a, MODELS_DIR / "svm_reg_a.pkl")
        joblib.dump(self.scaler, MODELS_DIR / "svm_scaler.pkl")

    def load(self) -> bool:
        try:
            self.clf = joblib.load(MODELS_DIR / "svm_clf.pkl")
            self.reg_h = joblib.load(MODELS_DIR / "svm_reg_h.pkl")
            self.reg_a = joblib.load(MODELS_DIR / "svm_reg_a.pkl")
            self.scaler = joblib.load(MODELS_DIR / "svm_scaler.pkl")
            self.is_fitted = True
            return True
        except Exception:
            return False


class GDAModel(BaseModel):
    def __init__(self):
        super().__init__("GDA")
        self.clf = LinearDiscriminantAnalysis()
        self.scaler = StandardScaler()

    def train(self, X: np.ndarray, y_res: np.ndarray, y_goals: np.ndarray = None):
        X_scaled = self.scaler.fit_transform(X)
        self.clf.fit(X_scaled, y_res)
        self.is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([[0.38, 0.28, 0.34]])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        return self.clf.predict_proba(X_scaled)

    def save(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, MODELS_DIR / "gda_clf.pkl")
        joblib.dump(self.scaler, MODELS_DIR / "gda_scaler.pkl")

    def load(self) -> bool:
        try:
            self.clf = joblib.load(MODELS_DIR / "gda_clf.pkl")
            self.scaler = joblib.load(MODELS_DIR / "gda_scaler.pkl")
            self.is_fitted = True
            return True
        except Exception:
            return False


class RandomForestModel(BaseModel):
    def __init__(self):
        super().__init__("RandomForest")
        self.clf = RandomForestClassifier(
            class_weight={0: 1.0, 1: 1.4, 2: 1.0},
            max_features=10,
            min_samples_leaf=5,
            n_estimators=1000,
            random_state=42
        )
        self.scaler = StandardScaler()

    def train(self, X: np.ndarray, y_res: np.ndarray, y_goals: np.ndarray = None):
        X_scaled = self.scaler.fit_transform(X)
        self.clf.fit(X_scaled, y_res)
        self.is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([[0.38, 0.28, 0.34]])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        return self.clf.predict_proba(X_scaled)

    def save(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, MODELS_DIR / "rf_clf.pkl")
        joblib.dump(self.scaler, MODELS_DIR / "rf_scaler.pkl")

    def load(self) -> bool:
        try:
            self.clf = joblib.load(MODELS_DIR / "rf_clf.pkl")
            self.scaler = joblib.load(MODELS_DIR / "rf_scaler.pkl")
            self.is_fitted = True
            return True
        except Exception:
            return False


class XGBoostModel(BaseModel):
    def __init__(self):
        super().__init__("XGBoost")
        self.clf = xgb.XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            eval_metric="mlogloss",
            tree_method="hist",
            max_depth=9,
            learning_rate=0.088,
            min_child_weight=3,
            gamma=4.77,
            subsample=0.906,
            colsample_bytree=0.5605,
            reg_alpha=2.611,
            reg_lambda=5.891,
            n_estimators=662,
            random_state=42
        )
        self.reg = MultiOutputRegressor(
            xgb.XGBRegressor(
                objective="reg:squarederror",
                tree_method="hist",
                max_depth=3,
                learning_rate=0.0798,
                min_child_weight=10,
                subsample=0.8548,
                colsample_bytree=0.9383,
                reg_alpha=0.9415,
                reg_lambda=6.087,
                n_estimators=341,
                random_state=42
            )
        )
        self.scaler = StandardScaler()

    def train(self, X: np.ndarray, y_res: np.ndarray, y_goals: np.ndarray = None):
        X_scaled = self.scaler.fit_transform(X)
        self.clf.fit(X_scaled, y_res)
        if y_goals is not None:
            self.reg.fit(X_scaled, y_goals)
        self.is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([[0.38, 0.28, 0.34]])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        return self.clf.predict_proba(X_scaled)

    def predict_goals(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([1.3, 1.1])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        return self.reg.predict(X_scaled)

    def save(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, MODELS_DIR / "xgb_clf.pkl")
        joblib.dump(self.reg, MODELS_DIR / "xgb_reg.pkl")
        joblib.dump(self.scaler, MODELS_DIR / "xgb_scaler.pkl")

    def load(self) -> bool:
        try:
            self.clf = joblib.load(MODELS_DIR / "xgb_clf.pkl")
            self.reg = joblib.load(MODELS_DIR / "xgb_reg.pkl")
            self.scaler = joblib.load(MODELS_DIR / "xgb_scaler.pkl")
            self.is_fitted = True
            return True
        except Exception:
            return False


class NeuralNetworkModel(BaseModel):
    def __init__(self):
        super().__init__("NeuralNetwork")
        self.clf = MLPClassifier(
            hidden_layer_sizes=(32,),
            activation='relu',
            solver='adam',
            learning_rate='adaptive',
            learning_rate_init=0.0001,
            max_iter=700,
            alpha=0.0005,
            batch_size=32,
            random_state=20
        )
        self.scaler = StandardScaler()

    def train(self, X: np.ndarray, y_res: np.ndarray, y_goals: np.ndarray = None):
        X_scaled = self.scaler.fit_transform(X)
        self.clf.fit(X_scaled, y_res)
        self.is_fitted = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            return np.array([[0.38, 0.28, 0.34]])
        X_scaled = self.scaler.transform(X.reshape(1, -1) if X.ndim == 1 else X)
        return self.clf.predict_proba(X_scaled)

    def save(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, MODELS_DIR / "nn_clf.pkl")
        joblib.dump(self.scaler, MODELS_DIR / "nn_scaler.pkl")

    def load(self) -> bool:
        try:
            self.clf = joblib.load(MODELS_DIR / "nn_clf.pkl")
            self.scaler = joblib.load(MODELS_DIR / "nn_scaler.pkl")
            self.is_fitted = True
            return True
        except Exception:
            return False
