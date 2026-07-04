import unittest
import sys
import os
import json
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestBotRename(unittest.TestCase):
    def test_legacy_state_migration(self):
        from src.market import paper_trading
        
        # Create a mock legacy paper_trading.json structure
        legacy_state = {
            "predict": {
                "big_d": {"bankroll": 950.0, "active_bets": [], "history": []},
                "sigmaballs": {"bankroll": 1050.0, "active_bets": [], "history": []}
            }
        }
        
        test_path = os.path.join("data", "processed", "paper_trading_test.json")
        with open(test_path, "w") as f:
            json.dump(legacy_state, f)
            
        # Patch FILE_PATH to point to test_path
        original_path = paper_trading.FILE_PATH
        paper_trading.FILE_PATH = test_path
        
        try:
            state = paper_trading.load_state()
            self.assertIn("magnus", state["predict"])
            self.assertIn("athena", state["predict"])
            self.assertEqual(state["predict"]["magnus"]["bankroll"], 950.0)
            self.assertEqual(state["predict"]["athena"]["bankroll"], 1050.0)
        finally:
            paper_trading.FILE_PATH = original_path
            if os.path.exists(test_path):
                os.remove(test_path)

if __name__ == '__main__':
    unittest.main()
