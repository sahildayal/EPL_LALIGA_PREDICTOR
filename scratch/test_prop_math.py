import sys
sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
import unittest
import numpy as np
from src.models.player_props import calculate_player_prop_probs

class TestPropMath(unittest.TestCase):
    def test_binomial_math(self):
        player_stats = {
            "goals_per_90": 0.5,
            "assists_per_90": 0.25
        }
        # Simple 2x2 score matrix
        matrix = np.zeros((3, 3))
        matrix[1, 0] = 0.5  # 50% chance of 1-0
        matrix[2, 0] = 0.5  # 50% chance of 2-0
        
        # Home team historical average = 1.0 goals per match
        probs = calculate_player_prop_probs(player_stats, is_home=True, score_matrix=matrix, team_historical_avg=1.0)
        
        # Goal Share = 0.5 / 1.0 = 0.5
        # At g=1: P(1+ goals) = 1 - 0.5^1 = 0.5
        # At g=2: P(1+ goals) = 1 - 0.5^2 = 0.75
        # Expected P(1+ goals) = 0.5 * 0.5 + 0.5 * 0.75 = 0.625
        self.assertAlmostEqual(probs["goals_1"], 0.625)

    def test_away_team_and_empty_stats(self):
        # Empty stats dict should fall back to defaults: goals_per_90=0.25, assists_per_90=0.15
        player_stats = {}
        
        matrix = np.zeros((3, 3))
        matrix[0, 1] = 1.0  # 100% chance of 0-1 (away team scores 1)
        
        # Away team historical avg = 0.5
        probs = calculate_player_prop_probs(player_stats, is_home=False, score_matrix=matrix, team_historical_avg=0.5)
        
        # s_g = 0.25 / 0.5 = 0.5
        # s_a = 0.15 / 0.5 = 0.3
        # s_ga = 0.5 + 0.3 = 0.8
        # Since away goals = 1 (g=1):
        # P(1+ goals) = 0.5
        # P(2+ goals) = 0.0
        # P(1+ assists) = 0.3
        # P(2+ assists) = 0.0
        # P(1+ goal/assist) = 0.8
        self.assertEqual(probs["goals_1"], 0.5)
        self.assertEqual(probs["goals_2"], 0.0)
        self.assertEqual(probs["assists_1"], 0.3)
        self.assertEqual(probs["assists_2"], 0.0)
        self.assertEqual(probs["goal_or_assist"], 0.8)

    def test_clamped_shares_and_low_average(self):
        player_stats = {
            "goals_per_90": 2.0,  # very high
            "assists_per_90": 1.0
        }
        matrix = np.zeros((3, 3))
        matrix[1, 1] = 1.0  # 100% chance of 1-1
        
        # Low average team goals will be clamped to 0.5 floor
        probs = calculate_player_prop_probs(player_stats, is_home=True, score_matrix=matrix, team_historical_avg=0.1)
        
        # avg_goals max floor = 0.5
        # s_g = min(2.0 / 0.5, 0.95) = 0.95 (clamped)
        # s_a = min(1.0 / 0.5, 0.95) = 0.95 (clamped)
        # s_ga = min(0.95 + 0.95, 0.95) = 0.95 (clamped)
        # Since home goals = 1:
        # P(1+ goals) = 0.95
        # P(1+ assists) = 0.95
        # P(1+ goal/assist) = 0.95
        self.assertEqual(probs["goals_1"], 0.95)
        self.assertEqual(probs["assists_1"], 0.95)
        self.assertEqual(probs["goal_or_assist"], 0.95)

if __name__ == "__main__":
    unittest.main()

