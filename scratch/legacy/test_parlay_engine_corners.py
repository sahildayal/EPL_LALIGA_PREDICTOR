import unittest
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestParlayEngineCorners(unittest.TestCase):
    @patch("src.parlay.parlay_engine.get_team_recent_corners")
    def test_corner_probabilities(self, mock_corners):
        # Mock home team (6 won, 4 conceded) and away team (5 won, 5 conceded)
        mock_corners.side_effect = lambda t: {"won": 6.0, "conceded": 4.0} if t == "brazil" else {"won": 5.0, "conceded": 5.0}
        
        from src.models.statistical import DixonColesModel
        from src.parlay.parlay_engine import ParlayEngine
        
        dc = DixonColesModel()
        engine = ParlayEngine(dc)
        
        # Expected total corners won = 6 + 5 = 11
        # Check probability over 8.5 corners
        p_over = engine.get_corners_probability("brazil", "japan", 8.5)
        self.assertTrue(0.0 <= p_over <= 1.0)
        self.assertTrue(p_over > 0.5)

if __name__ == '__main__':
    unittest.main()
