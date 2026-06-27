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

    def test_get_lineups_mocked_espn(self):
        from unittest.mock import patch, MagicMock
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "rosters": [
                {
                    "team": {"displayName": "Colombia"},
                    "roster": [
                        {"starter": True, "active": True, "athlete": {"displayName": "James Rodriguez"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Luis Diaz"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Jhon Cordoba"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Arias"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Rios"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Lerma"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Mojica"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Cuesta"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Sanchez"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Munoz"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Vargas"}},
                    ]
                },
                {
                    "team": {"displayName": "Portugal"},
                    "roster": [
                        {"starter": True, "active": True, "athlete": {"displayName": "Cristiano Ronaldo"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Joao Neves"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Bruno Fernandes"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Bernardo Silva"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Rafael Leao"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Vitinha"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Joao Cancelo"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Pepe"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Ruben Dias"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Diogo Dalot"}},
                        {"starter": True, "active": True, "athlete": {"displayName": "Diogo Costa"}},
                    ]
                }
            ]
        }
        
        with patch("requests.get", return_value=mock_response) as mock_get:
            res = get_match_lineups("Colombia", "Portugal", event_id="mock_event_123")
            mock_get.assert_called()
            self.assertEqual(res["source"], "live_espn_announcement")
            self.assertIn("james rodriguez", res["home_lineup"])
            self.assertIn("cristiano ronaldo", res["away_lineup"])
            self.assertEqual(len(res["home_lineup"]), 11)
            self.assertEqual(len(res["away_lineup"]), 11)

if __name__ == "__main__":
    unittest.main()
