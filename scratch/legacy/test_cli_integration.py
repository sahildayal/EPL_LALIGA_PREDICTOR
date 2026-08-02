import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestCliIntegration(unittest.TestCase):
    @patch("main.predict_match")
    @patch("main.get_team_recent_corners")
    def test_cli_forecast_outputs(self, mock_corners, mock_predict):
        mock_corners.return_value = {"won": 6.0, "conceded": 4.0}
        
        mock_res = MagicMock()
        mock_res.probabilities = {"home_win": 0.50, "draw": 0.20, "away_win": 0.30}
        mock_res.sentiment = 0.0
        mock_res.elo_diff = 0.0
        mock_res.progression_probabilities = {"home_advances": 0.60, "away_advances": 0.40}
        mock_predict.return_value = mock_res
        
        from main import run_predict
        # Verifies executing main prediction runs successfully without syntax exceptions
        try:
            run_predict("brazil vs japan")
            passed = True
        except Exception:
            passed = False
        self.assertTrue(passed)

if __name__ == '__main__':
    unittest.main()
