from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
import unittest
from src.data.team_mapping import is_team_match

class TestMarketMatch(unittest.TestCase):
    def test_market_title_checks(self):
        self.assertTrue(is_team_match("Joao Neves", "Joao Neves: 1+ assists?"))
        self.assertTrue(is_team_match("Joao Neves", "Joao Neves: score or assist?"))
        self.assertTrue(is_team_match("Joao Neves", "Joao Neves: 2+ goals"))

if __name__ == "__main__":
    unittest.main()
