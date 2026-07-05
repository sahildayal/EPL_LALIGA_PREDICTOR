import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestSgpExpansion(unittest.TestCase):
    def test_generate_combos_with_expanded_markets(self):
        from src.parlay.parlay_engine import ParlayEngine
        from src.models.statistical import DixonColesModel
        
        # Initialize mock DixonColes model
        model = DixonColesModel()
        dummy_matches = [
            {"home_team": "france", "away_team": "sweden", "home_goals": 2, "away_goals": 1},
            {"home_team": "brazil", "away_team": "japan", "home_goals": 3, "away_goals": 0}
        ]
        model.fit(dummy_matches)
        
        engine = ParlayEngine(model)
        
        # Setup mock match data containing Corners and To Advance odds with positive edge
        match_data = [
            {
                "home": "france",
                "away": "sweden",
                "market_odds": {
                    "home_win": 0.40,
                    "draw": 0.15,
                    "away_win": 0.15,
                    "over_1.5": 0.70,
                    "btts": 0.50,
                    "to_qualify_home": 0.40,
                    "to_qualify_away": 0.30,
                    "corners_over_7.5": 0.60,
                    "corners_over_8.5": 0.40,
                    "scorer_kylian_mbappe": 0.20,
                    "scorer_antoine_griezmann": 0.15
                },
                "players": [("kylian mbappe", True), ("antoine griezmann", True)]
            }
        ]
        
        combos = engine.generate_combos(match_data, max_legs=8, min_odds=2.0, max_odds=200.0)
        
        # Verify that candidates were generated for To Advance and Corners
        # and that some combos contain more than 4 legs
        self.assertTrue(len(combos) > 0)
        has_corners_leg = False
        has_to_advance_leg = False
        max_legs_found = 0
        for c in combos:
            max_legs_found = max(max_legs_found, len(c["legs"]))
            for leg in c["legs"]:
                if "corners" in leg.get("outcome", ""):
                    has_corners_leg = True
                if "to_qualify" in leg.get("outcome", ""):
                    has_to_advance_leg = True
                    
        self.assertTrue(has_corners_leg, "Should include corners outcomes in generated parlay legs")
        self.assertTrue(has_to_advance_leg, "Should include to_qualify outcomes in generated parlay legs")
        print(f"Max legs found in parlay combos: {max_legs_found}")
        self.assertTrue(max_legs_found >= 5, "Should generate combos with 5 or more legs")

if __name__ == '__main__':
    unittest.main()
