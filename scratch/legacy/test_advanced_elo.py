import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.models.advanced_elo import EloSystem

class TestAdvancedElo(unittest.TestCase):
    def test_elo_update(self):
        system = EloSystem(default_rating=1600, H=100)
        # Portugal defeats Spain 3-0 on neutral ground with World Cup Knockout K-factor (60)
        new_h, new_a = system.update_ratings("portugal", "spain", 3, 0, k_factor=60, is_neutral=True)
        self.assertTrue(new_h > 1600)
        self.assertTrue(new_a < 1600)

    def test_margin_of_victory_multiplier(self):
        # 1-0 win vs 3-0 win on neutral ground, same ratings, same K-factor
        sys1 = EloSystem(default_rating=1500, H=100)
        new_h1, new_a1 = sys1.update_ratings("teamA", "teamB", 1, 0, k_factor=40, is_neutral=True)
        change_1 = new_h1 - 1500
        
        sys2 = EloSystem(default_rating=1500, H=100)
        new_h2, new_a2 = sys2.update_ratings("teamA", "teamB", 3, 0, k_factor=40, is_neutral=True)
        change_2 = new_h2 - 1500
        
        # 3-0 win should have a larger update than 1-0 win due to the margin of victory multiplier (1.75 vs 1.0)
        self.assertAlmostEqual(change_2 / change_1, 1.75)
        self.assertTrue(change_2 > change_1)

    def test_k_factor_scaling(self):
        # Friendlies (K=20) vs World Cup Knockouts (K=60)
        sys1 = EloSystem(default_rating=1500, H=100)
        new_h1, _ = sys1.update_ratings("teamA", "teamB", 1, 0, k_factor=20, is_neutral=True)
        change_1 = new_h1 - 1500
        
        sys2 = EloSystem(default_rating=1500, H=100)
        new_h2, _ = sys2.update_ratings("teamA", "teamB", 1, 0, k_factor=60, is_neutral=True)
        change_2 = new_h2 - 1500
        
        # K=60 should result in 3x change compared to K=20
        self.assertAlmostEqual(change_2 / change_1, 3.0)

    def test_case_insensitivity_and_normalization(self):
        system = EloSystem(default_rating=1500, H=100)
        system.update_ratings("  PORtugal ", "SpaIN  ", 2, 1, k_factor=40, is_neutral=True)
        
        # Check rating retrieval is case insensitive and whitespace stripped
        r_por = system.get_rating("portugal")
        r_por2 = system.get_rating("  PORTUGAL  ")
        r_spa = system.get_rating("Spain")
        
        self.assertEqual(r_por, r_por2)
        self.assertTrue(r_por > 1500)
        self.assertTrue(r_spa < 1500)

    def test_home_advantage(self):
        system = EloSystem(default_rating=1500, H=100)
        # Calculate win expectancy with home advantage (is_neutral=False)
        we_home = system.calculate_win_expectancy(1500, 1500, is_home=True)
        # Calculate win expectancy without home advantage (is_neutral=True / is_home=False)
        we_neutral = system.calculate_win_expectancy(1500, 1500, is_home=False)
        
        self.assertTrue(we_home > 0.5)
        self.assertEqual(we_neutral, 0.5)

if __name__ == '__main__':
    unittest.main()
