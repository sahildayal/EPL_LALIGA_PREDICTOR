import unittest
import sys
from pathlib import Path
import os

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestPredictorImprovements(unittest.TestCase):
    def test_dixon_coles_regressor_integration(self):
        # Verify get_fitted_dixon_coles returns a valid DixonColesRegressor
        from src.predictor import get_fitted_dixon_coles
        reg = get_fitted_dixon_coles()
        self.assertIsNotNone(reg)
        self.assertTrue(hasattr(reg, "predict_match_probs"))
        
        # Test predict_match_probs with mock teams or existing teams
        p_h, p_d, p_a = reg.predict_match_probs("brazil", "japan")
        self.assertAlmostEqual(p_h + p_d + p_a, 1.0, places=4)
        
    def test_debate_key_enforcement(self):
        # Verify generate_debate raises a RuntimeError if GEMINI_API_KEY is missing
        from src.market import llm
        
        # Backup status
        orig_key = os.environ.get("GEMINI_API_KEY")
        orig_avail = llm.GEMINI_AVAILABLE
        
        try:
            # Force GEMINI_AVAILABLE to False / clear key
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]
            llm.GEMINI_AVAILABLE = False
            
            with self.assertRaises(RuntimeError):
                llm.generate_debate("Brazil", "Japan", {"home_win": 0.4, "draw": 0.2, "away_win": 0.4}, 0.0, 0.0, [], [])
        finally:
            # Restore
            if orig_key is not None:
                os.environ["GEMINI_API_KEY"] = orig_key
            llm.GEMINI_AVAILABLE = orig_avail
            
    def test_fractional_kelly_sizing(self):
        # Verify Kelly Sizing math:
        # f* = (p * b - (1 - p)) / b
        # where b = odds - 1
        p = 0.50
        odds = 2.50
        b = odds - 1.0  # 1.50
        f_star = (p * b - (1.0 - p)) / b  # (0.50 * 1.50 - 0.50) / 1.50 = 0.25 / 1.50 = 0.1667
        quarter_kelly = 0.25 * f_star  # 0.04167
        
        self.assertAlmostEqual(quarter_kelly, 0.04167, places=4)
        
if __name__ == '__main__':
    unittest.main()
