import unittest
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.models.simulation import run_tournament_simulation, get_goalie_rate

class TestMonteCarlo(unittest.TestCase):
    def test_simulation_probabilities_sum_to_one(self):
        results = run_tournament_simulation(num_runs=100)
        self.assertIn("probabilities", results)
        
        # Assert that sum of champion probabilities is approx 1.0 (100%)
        total_champ = sum(t["champion"] for t in results["probabilities"])
        self.assertAlmostEqual(total_champ, 1.0, places=2)
        
        # All 8 teams should have 100% (1.0) of reaching quarterfinals since they start there
        for t in results["probabilities"]:
            self.assertEqual(t["quarterfinals"], 1.0)

    def test_custom_teams_simulation(self):
        custom_teams = ["Argentina", "France", "Brazil", "England", "Spain", "Portugal", "Netherlands", "Norway"]
        results = run_tournament_simulation(num_runs=100, teams=custom_teams)
        
        # Verify result contains all normalized custom teams
        simulated_teams = [t["team"] for t in results["probabilities"]]
        expected_teams = [t.lower().strip() for t in custom_teams]
        self.assertEqual(set(simulated_teams), set(expected_teams))
        
        # Validate sum of champion probabilities
        total_champ = sum(t["champion"] for t in results["probabilities"])
        self.assertAlmostEqual(total_champ, 1.0, places=2)

    def test_team_length_validation(self):
        # Passing 7 teams should raise ValueError
        with self.assertRaises(ValueError):
            run_tournament_simulation(num_runs=10, teams=["brazil"] * 7)
            
        # Passing 9 teams should raise ValueError
        with self.assertRaises(ValueError):
            run_tournament_simulation(num_runs=10, teams=["brazil"] * 9)

    def test_case_insensitive_matching(self):
        # Test case-insensitivity of team names in simulation
        custom_teams = ["ArGeNtInA", "FrAnCe", "BrAzIl", "EnGlAnD", "SpAiN", "PoRtUgAl", "NeThErLaNdS", "GeRmAnY"]
        results = run_tournament_simulation(num_runs=50, teams=custom_teams)
        
        simulated_teams = [t["team"] for t in results["probabilities"]]
        expected_teams = [t.lower().strip() for t in custom_teams]
        self.assertEqual(set(simulated_teams), set(expected_teams))

    def test_goalie_save_rates(self):
        # Verify goalie profiles and fallbacks
        self.assertEqual(get_goalie_rate("brazil"), 0.33)
        self.assertEqual(get_goalie_rate("BRAZIL"), 0.33)
        self.assertEqual(get_goalie_rate("england"), 0.28)
        self.assertEqual(get_goalie_rate("japan"), 0.25)
        
        # Non-mapped team should fallback to 0.25
        self.assertEqual(get_goalie_rate("france"), 0.25)

if __name__ == "__main__":
    unittest.main()
