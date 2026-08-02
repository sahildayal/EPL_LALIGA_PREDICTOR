import unittest
import sys
import os
import shutil
import tempfile
import json
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestParlayUpdateFix(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.patch_state_path = os.path.join(self.test_dir, "paper_trading.json")
        
        # Initialize clean state file
        from src.market import paper_trading
        self.old_state_path = paper_trading.FILE_PATH
        paper_trading.FILE_PATH = self.patch_state_path
        
        # Write clean empty portfolios state
        state = {
            "parlay_longshot": {
                "magnus": {"bankroll": 1000.0, "active_bets": [], "history": []},
                "athena": {"bankroll": 1000.0, "active_bets": [], "history": []}
            }
        }
        with open(self.patch_state_path, "w") as f:
            json.dump(state, f)

    def tearDown(self):
        from src.market import paper_trading
        paper_trading.FILE_PATH = self.old_state_path
        shutil.rmtree(self.test_dir)

    def test_parlay_bet_update_legs_or_stake_diff(self):
        from src.market import paper_trading
        
        # Place initial card
        legs_1 = [{"home": "france", "away": "brazil", "bet_type": "Moneyline - France Win", "result": "pending"}]
        res1 = paper_trading.update_bet(
            "parlay_longshot", "magnus", "parlay", "longshot_1",
            "Longshot Card #1 (1 legs)", 33.0, 10.0, is_parlay=True, legs=legs_1
        )
        self.assertEqual(res1["action"], "placed")
        
        # Try placing identical - should return none
        res2 = paper_trading.update_bet(
            "parlay_longshot", "magnus", "parlay", "longshot_1",
            "Longshot Card #1 (1 legs)", 33.0, 10.0, is_parlay=True, legs=legs_1
        )
        self.assertEqual(res2["action"], "none")
        
        # Try placing with different stake - should update/replace and refund
        res3 = paper_trading.update_bet(
            "parlay_longshot", "magnus", "parlay", "longshot_1",
            "Longshot Card #1 (1 legs)", 2.0, 10.0, is_parlay=True, legs=legs_1
        )
        self.assertEqual(res3["action"], "updated")
        
        # Verify bankroll: 1000 - 33 initially, then + 33 refund, then - 2 = 998.0
        state = paper_trading.load_state()
        self.assertAlmostEqual(state["parlay_longshot"]["magnus"]["bankroll"], 998.0)
        
        # Try placing with different legs - should update/replace
        legs_2 = [{"home": "france", "away": "brazil", "bet_type": "Moneyline - Draw", "result": "pending"}]
        res4 = paper_trading.update_bet(
            "parlay_longshot", "magnus", "parlay", "longshot_1",
            "Longshot Card #1 (1 legs)", 2.0, 12.0, is_parlay=True, legs=legs_2
        )
        self.assertEqual(res4["action"], "updated")

if __name__ == '__main__':
    unittest.main()
