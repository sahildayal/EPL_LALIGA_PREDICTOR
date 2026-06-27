import sys
sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
import unittest
from src.data.scrapers.fixtures import get_match_lineups

class TestLineups(unittest.TestCase):
    def test_get_lineups_with_stubbed_id(self):
        # Test with a dummy event ID or real ESPN soccer event ID
        res = get_match_lineups("Colombia", "Portugal", event_id="401642878")
        self.assertIn("home_lineup", res)
        self.assertIn("away_lineup", res)
        self.assertEqual(res["source"], "fallback_recent_or_default")
        # Colombia default players
        self.assertIn("james rodriguez", res["home_lineup"])
        # Portugal default players
        self.assertIn("cristiano ronaldo", res["away_lineup"])

    def test_get_lineups_fallback_default_generic(self):
        # Test fallback for a team not in DEFAULT_PLAYERS (e.g., Nepal)
        res = get_match_lineups("Nepal", "Germany")
        self.assertEqual(res["home_lineup"], ["player1", "player2", "player3"])
        self.assertIn("jamal musiala", res["away_lineup"])
        self.assertEqual(res["source"], "fallback_recent_or_default")

    def test_get_lineups_case_insensitive_normalization(self):
        # Test case-insensitivity and aliases
        res = get_match_lineups("COLOMBIA", "portugal")
        self.assertIn("james rodriguez", res["home_lineup"])
        self.assertIn("cristiano ronaldo", res["away_lineup"])

    def test_fetch_team_recent_lineup_invalid_team(self):
        # Test that _fetch_team_recent_lineup returns empty list for invalid team
        from src.data.scrapers.fixtures import _fetch_team_recent_lineup
        res = _fetch_team_recent_lineup("invalid_team_name")
        self.assertEqual(res, [])

if __name__ == "__main__":
    unittest.main()
