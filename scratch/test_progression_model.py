import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestProgressionModel(unittest.TestCase):
    def test_advancement_probabilities_brazil_japan(self):
        from src.predictor import predict_match
        res = predict_match("brazil", "japan")
        self.assertTrue(hasattr(res, "progression_probabilities"))
        p_h = res.progression_probabilities["home_advances"]
        p_a = res.progression_probabilities["away_advances"]
        self.assertAlmostEqual(p_h + p_a, 1.0, places=4)
        # Brazil has higher Elo (2049 vs 1869) and better goalie rate (33% vs 25%)
        # So Brazil should have a significantly higher progression probability
        self.assertTrue(p_h > 0.70)
        self.assertTrue(p_h > p_a)

    def test_advancement_probabilities_japan_brazil(self):
        from src.predictor import predict_match
        res = predict_match("japan", "brazil")
        p_h = res.progression_probabilities["home_advances"]
        p_a = res.progression_probabilities["away_advances"]
        self.assertAlmostEqual(p_h + p_a, 1.0, places=4)
        # Japan is home but Brazil has much higher Elo and better goalie rate
        # So Brazil (away advances) should still be favored
        self.assertTrue(p_a > p_h)

    def test_default_goalkeeper_rates(self):
        from src.predictor import predict_match
        # Using two teams not in the explicit goalkeeper mapping (e.g. France vs England)
        res = predict_match("france", "england")
        p_h = res.progression_probabilities["home_advances"]
        p_a = res.progression_probabilities["away_advances"]
        self.assertAlmostEqual(p_h + p_a, 1.0, places=4)

if __name__ == '__main__':
    unittest.main()
