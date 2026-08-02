import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestLargeLegs(unittest.TestCase):
    def test_high_leg_generation(self):
        from src.models.statistical import DixonColesModel
        from src.parlay.parlay_engine import ParlayEngine
        
        dc = DixonColesModel()
        engine = ParlayEngine(dc)
        
        # Setup mock data with 12 positive-edge candidates (moderate market odds to allow 5+ leg combos)
        match_data = [
            {
                "home": "France", "away": "Brazil",
                "market_odds": {
                    "home_win": 0.1, "draw": 0.1, "away_win": 0.1,
                    "over_1.5": 0.1, "over_2.5": 0.1, "btts": 0.1
                }
            },
            {
                "home": "Argentina", "away": "England",
                "market_odds": {
                    "home_win": 0.1, "draw": 0.1, "away_win": 0.1,
                    "over_1.5": 0.1, "over_2.5": 0.1, "btts": 0.1
                }
            }
        ]
        
        # Request up to 10 legs with min_odds=50000.0 to filter out lower leg count combinations
        combos = engine.generate_combos(match_data, max_legs=10, min_odds=50000.0, max_odds=1000000.0)
        self.assertGreater(len(combos), 0)
        # Check that we got at least one combo with more than 5 legs
        high_legs = [c for c in combos if len(c["legs"]) >= 5]
        self.assertGreater(len(high_legs), 0)

if __name__ == '__main__':
    unittest.main()
