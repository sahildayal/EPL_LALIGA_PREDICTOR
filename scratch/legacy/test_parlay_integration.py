import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestParlayIntegration(unittest.TestCase):
    def test_same_game_parlay_correlations(self):
        from src.models.statistical import DixonColesModel
        from src.parlay.parlay_engine import ParlayEngine
        
        dc = DixonColesModel()
        engine = ParlayEngine(dc)
        
        # Test SGP combining goals, corners, and qualification
        outcomes_full = ["home_win", "over_2.5", "to_qualify_home", "corners_over_8.5"]
        outcomes_no_corners = ["home_win", "over_2.5", "to_qualify_home"]
        outcomes_no_qualify = ["home_win", "over_2.5", "corners_over_8.5"]
        
        with patch.object(engine, "get_corners_probability", return_value=0.70):
            p_full = engine.get_same_game_joint_prob("brazil", "japan", outcomes_full)
            p_no_corners = engine.get_same_game_joint_prob("brazil", "japan", outcomes_no_corners)
            p_no_qualify = engine.get_same_game_joint_prob("brazil", "japan", outcomes_no_qualify)
            
            # Assert probabilities are valid
            self.assertTrue(0.0 <= p_full <= 1.0)
            self.assertTrue(0.0 <= p_no_corners <= 1.0)
            self.assertTrue(0.0 <= p_no_qualify <= 1.0)
            
            # Corner probability multiplier is independent: p_full should be p_no_corners * 0.70
            self.assertAlmostEqual(p_full, p_no_corners * 0.70, places=4)
            
            # Since 'home_win' regulation outcome is required, the team MUST win in regulation to satisfy the bet,
            # which implies they automatically qualify. Hence, adding 'to_qualify_home' should not change the probability.
            self.assertAlmostEqual(p_full, p_no_qualify, places=4)

if __name__ == '__main__':
    unittest.main()
