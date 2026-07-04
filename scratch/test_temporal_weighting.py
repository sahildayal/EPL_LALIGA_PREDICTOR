import unittest
import sys
import pandas as pd
import numpy as np
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestTemporalWeighting(unittest.TestCase):
    def test_weight_decay_calculation(self):
        from src.models.trainer import calculate_sample_weights
        
        # Match dates: 1 today, 1 four years ago (~1461 days), 1 eight years ago, 1 100 years ago (clamped)
        dates = pd.to_datetime([
            pd.Timestamp.now(),
            pd.Timestamp.now() - pd.Timedelta(days=1461),
            pd.Timestamp.now() - pd.Timedelta(days=1461 * 2),
            pd.Timestamp.now() - pd.Timedelta(days=36525)
        ])
        
        weights = calculate_sample_weights(dates)
        
        self.assertEqual(len(weights), 4)
        self.assertAlmostEqual(weights[0], 1.0, places=2)
        self.assertAlmostEqual(weights[1], 0.5, places=2)
        self.assertAlmostEqual(weights[2], 0.25, places=2)
        # Clamped at 0.05
        self.assertAlmostEqual(weights[3], 0.05, places=2)

    def test_timezone_and_nan_safety(self):
        from src.models.trainer import calculate_sample_weights
        
        # Test timezone-aware datetime and NaT/invalid dates
        dates = pd.Series([
            pd.Timestamp.now(tz="UTC"),
            pd.NaT,
            "invalid-date-string"
        ])
        
        weights = calculate_sample_weights(dates)
        self.assertEqual(len(weights), 3)
        # Timezone-aware should succeed and be close to 1.0; NaT/invalid should default to 0.05
        self.assertAlmostEqual(weights[0], 1.0, places=2)
        self.assertAlmostEqual(weights[1], 0.05, places=2)
        self.assertAlmostEqual(weights[2], 0.05, places=2)

    def test_model_training_with_weights(self):
        from src.models.machine_learning import (
            LogisticRegressionModel, SVMModel, GDAModel,
            RandomForestModel, XGBoostModel, NeuralNetworkModel
        )
        
        # Create a simple mock dataset (31 features to match FEATURE_NAMES length)
        X = np.random.randn(10, 31)
        y_res = np.random.choice([0, 1, 2], size=10)
        y_goals = np.random.randint(0, 5, size=(10, 2))
        sample_weight = np.random.uniform(0.05, 1.0, size=10)
        
        models = [
            LogisticRegressionModel(),
            SVMModel(),
            GDAModel(),
            RandomForestModel(),
            XGBoostModel(),
            NeuralNetworkModel()
        ]
        
        for model in models:
            # Test training with sample weights
            if model.model_name in ("LogisticRegression", "SupportVectorMachine", "XGBoost"):
                model.train(X, y_res, y_goals, sample_weight=sample_weight)
            else:
                model.train(X, y_res, sample_weight=sample_weight)
            self.assertTrue(model.is_fitted)

if __name__ == '__main__':
    unittest.main()
