import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json
import pandas as pd
import tempfile
import shutil
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestLongshotPortfolio(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for isolated test data files
        self.test_dir = tempfile.mkdtemp()
        self.stats_path = os.path.join(self.test_dir, "tournament_player_stats.json")
        self.master_path = os.path.join(self.test_dir, "master_dataset.csv")

        # Create dummy tournament stats
        self.tourney_stats = {
            "goals": {
                "mbappe": 4.0,
                "messi": 2.0
            },
            "assists": {}
        }
        with open(self.stats_path, "w") as f:
            json.dump(self.tourney_stats, f)

        # Create dummy master dataset to count matches
        # HomeTeam: France, AwayTeam: Brazil
        # So France has 3 matches (2 home, 1 away) in this CSV
        # Argentina has 2 matches
        df = pd.DataFrame([
            {"HomeTeam": "France", "AwayTeam": "Brazil"},
            {"HomeTeam": "France", "AwayTeam": "Argentina"},
            {"HomeTeam": "Argentina", "AwayTeam": "France"}
        ])
        df.to_csv(self.master_path, index=False)

        # Mock the path constants in parlay_engine
        self.patch_stats_path = patch("src.parlay.parlay_engine.STATS_PATH", self.stats_path)
        self.patch_master_path = patch("src.parlay.parlay_engine.MASTER_PATH", self.master_path)
        self.patch_stats_path.start()
        self.patch_master_path.start()

    def tearDown(self):
        self.patch_stats_path.stop()
        self.patch_master_path.stop()
        shutil.rmtree(self.test_dir)

    def test_diverse_portfolio_selection(self):
        from src.models.statistical import DixonColesModel
        from src.parlay.parlay_engine import ParlayEngine

        # We construct mock candidate parlays that share legs to verify diversity filtering.
        # Suppose we generate parlays. We want to verify that the selection algorithm
        # enforces that no two selected parlays share more than 2 legs.
        dc = DixonColesModel()
        engine = ParlayEngine(dc)

        # Let's create a scenario where we have multiple parlays:
        # Parlay A: Leg1, Leg2, Leg3 (edge 0.2, odds 15.0)
        # Parlay B: Leg1, Leg2, Leg3, Leg4 (edge 0.18, odds 20.0) -> Shares 3 legs with A! (should be excluded)
        # Parlay C: Leg1, Leg2, Leg5 (edge 0.15, odds 12.0) -> Shares 2 legs with A. (should be included)
        # Parlay D: Leg1, Leg6, Leg7 (edge 0.12, odds 10.0) -> Shares 1 leg with A and C. (should be included)
        
        match_data = [
            {
                "home": "France", "away": "Brazil",
                "market_odds": {
                    "home_win": 0.01,
                    "draw": 0.01,
                    "away_win": 0.01,
                    "over_1.5": 0.01,
                    "over_2.5": 0.01,
                    "btts": 0.01,
                    "scorer_mbappe": 0.01
                },
                "players": [("mbappe", True)]
            },
            {
                "home": "Argentina", "away": "England",
                "market_odds": {
                    "home_win": 0.02,
                    "draw": 0.02,
                    "away_win": 0.02,
                    "over_1.5": 0.02,
                    "over_2.5": 0.02,
                    "btts": 0.02
                },
                "players": []
            }
        ]

        # Let's verify parlay generation with min_odds >= 10.0 returns a diverse portfolio.
        # Since generating exact matches from real model might not trigger our specific overlapping,
        # we can mock or construct candidates to test the selection code directly, or we can mock
        # generate_combos logic or test the portfolio diversity selection loop.
        # Let's write a test that verifies the actual generate_combos return behavior and also
        # verifies the player stats blending.

        # Let's mock player_stats.get_player_stats to return a known value.
        with patch("src.data.scrapers.player_stats.get_player_stats") as mock_get_stats, \
             patch("src.parlay.parlay_engine.fbref_avg_goals") as mock_fbref_avg, \
             patch("src.parlay.parlay_engine.get_team_recent_corners") as mock_corners:
            mock_get_stats.return_value = {"goals_per_90": 0.8}
            mock_fbref_avg.return_value = 1.5
            mock_corners.return_value = {"won": 5.0, "conceded": 5.0}
            
            # Run generate_combos with min_odds=10.0
            combos = engine.generate_combos(match_data, max_legs=4, min_odds=10.0, max_odds=1000000.0)
            print(f"\n[DEBUG] len(combos) = {len(combos)}")
            
            # Assert that len(combos) > 0 to verify selection is executing.
            self.assertGreater(len(combos), 0, "generate_combos returned an empty portfolio!")
            
            # Assert all returned combos do not share more than 2 legs
            for i, p1 in enumerate(combos):
                for j, p2 in enumerate(combos):
                    if i == j:
                        continue
                    shared = sum(1 for leg1 in p1["legs"] for leg2 in p2["legs"] if leg1["description"] == leg2["description"])
                    self.assertLessEqual(shared, 2, f"Combo {i} and {j} share {shared} legs, which exceeds the limit of 2!")

    def test_player_stats_blending(self):
        from src.models.statistical import DixonColesModel
        from src.parlay.parlay_engine import ParlayEngine

        dc = DixonColesModel()
        engine = ParlayEngine(dc)

        # Player "mbappe" has 4 WC goals in 3 matches -> 1.33 goals/90 in WC.
        # Season stats: goals_per_90 = 0.8.
        # Blended: 0.5 * 0.8 + 0.5 * (4/3) = 0.4 + 0.6667 = 1.0667 goals/90.
        # Let's verify that the blended goals/90 is used in the model.
        # We can mock get_player_stats and check the resulting candidate model probability.
        with patch("src.data.scrapers.player_stats.get_player_stats") as mock_get_stats:
            mock_get_stats.return_value = {"goals_per_90": 0.8}
            
            # Let's call a helper or extract the share logic to test it.
            # We want to check that mbappe's blended rate is around 1.0667, and if we change his WC goals,
            # the probability/share changes correspondingly.
            
            # Let's define the match
            match = {
                "home": "France", "away": "Brazil",
                "market_odds": {
                    "scorer_mbappe": 0.4
                },
                "players": [("mbappe", True)]
            }
            
            # If we call generate_combos, we can inspect candidates or the generated probability.
            # Let's verify the engine loads the tourney stats correctly and computes the blended share.
            # To test this precisely, let's write a unit test for a helper method we will introduce.
            # e.g., engine.get_blended_player_g90("mbappe", "France")
            
            # Let's check get_blended_player_g90:
            # For mbappe: 0.5 * 0.8 + 0.5 * (4.0 / 3.0) = 1.0667
            g90 = engine.get_blended_player_g90("mbappe", "France", {"goals_per_90": 0.8})
            self.assertAlmostEqual(g90, 0.5 * 0.8 + 0.5 * (4.0 / 3.0), places=4)

if __name__ == '__main__':
    unittest.main()
