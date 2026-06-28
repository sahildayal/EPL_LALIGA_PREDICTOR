import unittest
import numpy as np
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# Add project root to path
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

if __name__ == '__main__':
    unittest.main()
