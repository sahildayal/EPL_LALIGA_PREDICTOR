import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestConfedCalibration(unittest.TestCase):
    def test_confederation_boosting(self):
        from src.predictor import ELO_PREDICTOR, predict_match
        # Explicitly set ELOs to match the task brief baseline (2037.0 - 1874.9 = 162.1)
        ELO_PREDICTOR.set("brazil", 2037.0)
        ELO_PREDICTOR.set("japan", 1874.9)
        
        # Brazil (CONMEBOL) vs Japan (AFC). Check Elo calibration.
        res = predict_match("brazil", "japan")
        # Brazil ELO boost (+50) minus Japan ELO penalty (-20) = 70 rating points shift
        self.assertEqual(res.elo_diff, 232.1) # rating diff (162.1) + confed diff (70.0)

if __name__ == '__main__':
    unittest.main()
