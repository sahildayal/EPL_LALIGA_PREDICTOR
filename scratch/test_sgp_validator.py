import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestSgpValidator(unittest.TestCase):
    def test_validator_rules(self):
        from src.parlay.sgp_validator import SgpSandboxValidator
        
        # 1. Valid combo
        valid_combo = [
            {"match": ("france", "sweden"), "outcome": "home_win", "type": "game_line"},
            {"match": ("france", "sweden"), "outcome": "over_2.5", "type": "game_line"},
            {"match": ("brazil", "japan"), "outcome": "home_win", "type": "game_line"}
        ]
        self.assertTrue(SgpSandboxValidator.validate_combo(valid_combo))
        
        # 2. BTTS + Over 1.5 - Blocked
        btts_over_15 = [
            {"match": ("france", "sweden"), "outcome": "btts", "type": "game_line"},
            {"match": ("france", "sweden"), "outcome": "over_1.5", "type": "game_line"}
        ]
        self.assertFalse(SgpSandboxValidator.validate_combo(btts_over_15))
        
        # 3. BTTS + Over 2.5 - Allowed
        btts_over_25 = [
            {"match": ("france", "sweden"), "outcome": "btts", "type": "game_line"},
            {"match": ("france", "sweden"), "outcome": "over_2.5", "type": "game_line"}
        ]
        self.assertTrue(SgpSandboxValidator.validate_combo(btts_over_25))
        
        # 4. Moneyline + To Advance - Blocked
        ml_to_advance = [
            {"match": ("france", "sweden"), "outcome": "home_win", "type": "game_line"},
            {"match": ("france", "sweden"), "outcome": "to_qualify_home", "type": "game_line"}
        ]
        self.assertFalse(SgpSandboxValidator.validate_combo(ml_to_advance))
        
        # 5. Spread + Moneyline - Blocked
        spread_ml = [
            {"match": ("france", "sweden"), "outcome": "spread_home", "type": "game_line"},
            {"match": ("france", "sweden"), "outcome": "home_win", "type": "game_line"}
        ]
        self.assertFalse(SgpSandboxValidator.validate_combo(spread_ml))
        
        # 6. Player goal + Over 0.5 - Blocked
        player_over_05 = [
            {"match": ("france", "sweden"), "player": "mbappe", "type": "player_prop"},
            {"match": ("france", "sweden"), "outcome": "over_0.5", "type": "game_line"}
        ]
        self.assertFalse(SgpSandboxValidator.validate_combo(player_over_05))

if __name__ == '__main__':
    unittest.main()
