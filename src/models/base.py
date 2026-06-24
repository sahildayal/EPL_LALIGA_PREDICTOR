from abc import ABC, abstractmethod
import numpy as np


class BaseModel(ABC):
    """
    Abstract base class for all prediction models.
    """

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.is_fitted = False

    @abstractmethod
    def train(self, X: np.ndarray, y: np.ndarray):
        """Train the model on features X and labels y."""
        pass

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probabilities for classes: [Home Win, Draw, Away Win]."""
        pass
