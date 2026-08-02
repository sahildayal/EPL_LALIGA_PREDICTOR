import unittest
import pandas as pd
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.models.dixon_coles_decay import DixonColesRegressor

class TestDixonColesDecay(unittest.TestCase):
    def test_regressor_fit(self):
        df = pd.DataFrame([
            {"home_team": "england", "away_team": "france", "home_goals": 2, "away_goals": 1, "days_ago": 2},
            {"home_team": "france", "away_team": "england", "home_goals": 0, "away_goals": 3, "days_ago": 10},
            {"home_team": "england", "away_team": "germany", "home_goals": 1, "away_goals": 1, "days_ago": 50}
        ])
        reg = DixonColesRegressor(xi=0.0019)
        reg.fit(df)
        p_h, p_d, p_a = reg.predict_match_probs("england", "france")
        self.assertTrue(0.0 <= p_h <= 1.0)
        self.assertTrue(0.0 <= p_d <= 1.0)
        self.assertTrue(0.0 <= p_a <= 1.0)
        self.assertAlmostEqual(p_h + p_d + p_a, 1.0, places=4)

    def test_unknown_teams(self):
        df = pd.DataFrame([
            {"home_team": "england", "away_team": "france", "home_goals": 2, "away_goals": 1, "days_ago": 2},
            {"home_team": "france", "away_team": "england", "home_goals": 0, "away_goals": 3, "days_ago": 10}
        ])
        reg = DixonColesRegressor(xi=0.0019)
        reg.fit(df)
        
        # Unknown away team
        p_h, p_d, p_a = reg.predict_match_probs("england", "unknown_team")
        self.assertAlmostEqual(p_h, 0.33)
        self.assertAlmostEqual(p_d, 0.33)
        self.assertAlmostEqual(p_a, 0.34)
        
        # Unknown home team
        p_h, p_d, p_a = reg.predict_match_probs("unknown_team", "france")
        self.assertAlmostEqual(p_h, 0.33)
        self.assertAlmostEqual(p_d, 0.33)
        self.assertAlmostEqual(p_a, 0.34)

    def test_fallback_fit_failure(self):
        # Pass data that is problematic or empty to trigger fit fallback
        df = pd.DataFrame(columns=["home_team", "away_team", "home_goals", "away_goals", "days_ago"])
        reg = DixonColesRegressor(xi=0.0019)
        
        # Fitting empty data does not raise an exception and sets fallback parameters
        reg.fit(df)
        self.assertIn('alphas', reg.params)
        self.assertEqual(len(reg.params['alphas']), 0)
        self.assertIn('betas', reg.params)
        self.assertEqual(len(reg.params['betas']), 0)
        self.assertEqual(reg.params['gamma'], 0.2)
        self.assertEqual(reg.params['rho'], 0.05)
        
        # Try checking with minimal teams (1 team or less)
        df_one = pd.DataFrame([
            {"home_team": "england", "away_team": "france", "home_goals": 2, "away_goals": 1, "days_ago": 2}
        ])
        reg_one = DixonColesRegressor(xi=0.0019)
        reg_one.fit(df_one)
        p_h, p_d, p_a = reg_one.predict_match_probs("england", "france")
        self.assertTrue(0.0 <= p_h <= 1.0)
        self.assertTrue(0.0 <= p_d <= 1.0)
        self.assertTrue(0.0 <= p_a <= 1.0)
        self.assertAlmostEqual(p_h + p_d + p_a, 1.0, places=4)

    def test_case_insensitivity_and_whitespace(self):
        df = pd.DataFrame([
            {"home_team": "England", "away_team": " France", "home_goals": 2, "away_goals": 1, "days_ago": 2},
            {"home_team": "france", "away_team": "england", "home_goals": 0, "away_goals": 3, "days_ago": 10}
        ])
        reg = DixonColesRegressor(xi=0.0019)
        reg.fit(df)
        
        # Check that mixed casing and leading/trailing whitespace still maps correctly in predict_match_probs
        p_h1, p_d1, p_a1 = reg.predict_match_probs("England", " France ")
        p_h2, p_d2, p_a2 = reg.predict_match_probs("england", "france")
        
        self.assertEqual(p_h1, p_h2)
        self.assertEqual(p_d1, p_d2)
        self.assertEqual(p_a1, p_a2)

if __name__ == '__main__':
    unittest.main()

