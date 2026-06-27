import sys
sys.path.append(r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor")
import unittest
from unittest.mock import patch, MagicMock
from src.data.scrapers.fixtures import get_match_lineups

class TestLineups(unittest.TestCase):
    def setUp(self):
        # Start patching requests.get globally for all tests in this class to avoid live network hits
        self.patcher = patch("requests.get")
        self.mock_get = self.patcher.start()
        
        # Start patching cache get and set globally to keep tests offline/isolated
        self.cache_get_patcher = patch("src.data.cache.get", return_value=None)
        self.cache_set_patcher = patch("src.data.cache.set")
        self.cache_get_patcher.start()
        self.cache_set_patcher.start()
        
        # Default mock response is empty/404 to simulate offline or no data, forcing default fallback instantly
        self.default_mock_response = MagicMock()
        self.default_mock_response.status_code = 404
        self.default_mock_response.json.return_value = {}
        self.mock_get.return_value = self.default_mock_response

    def tearDown(self):
        self.patcher.stop()
        self.cache_get_patcher.stop()
        self.cache_set_patcher.stop()

    def test_get_lineups_with_stubbed_id(self):
        # Patch requests.get to return a mock response that simulates the rosters structure
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
        self.mock_get.return_value = mock_response

        res = get_match_lineups("Colombia", "Portugal", event_id="401642878")
        self.assertIn("home_lineup", res)
        self.assertIn("away_lineup", res)
        self.assertEqual(res["source"], "live_espn_announcement")
        self.assertIn("james rodriguez", res["home_lineup"])
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
        # This will use the localized mock response via standard patch
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
        
        # Locally replace the active patch mock
        self.mock_get.return_value = mock_response
        res = get_match_lineups("Colombia", "Portugal", event_id="mock_event_123")
        self.assertEqual(res["source"], "live_espn_announcement")
        self.assertIn("james rodriguez", res["home_lineup"])
        self.assertIn("cristiano ronaldo", res["away_lineup"])
        self.assertEqual(len(res["home_lineup"]), 11)
        self.assertEqual(len(res["away_lineup"]), 11)

    def test_find_espn_event_id_success(self):
        from src.data.scrapers.fixtures import _find_espn_event_id
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "events": [
                {
                    "id": "mock_event_12345",
                    "name": "United States vs Colombia",
                    "competitions": [
                        {
                            "competitors": [
                                {"team": {"displayName": "United States"}},
                                {"team": {"displayName": "Colombia"}}
                            ]
                        }
                    ]
                }
            ]
        }
        self.mock_get.return_value = mock_response
        
        # USA has alias "usa" which maps to "usa" (canonical for "united states")
        # Colombia has canonical "colombia"
        event_id = _find_espn_event_id("usa", "colombia")
        self.assertEqual(event_id, "mock_event_12345")

    def test_fetch_team_recent_lineup_success(self):
        from src.data.scrapers.fixtures import _fetch_team_recent_lineup
        
        def mock_get_side_effect(url, *args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "scoreboard" in url:
                mock_resp.json.return_value = {
                    "events": [
                        {
                            "status": {"type": {"name": "STATUS_FINAL"}},
                            "competitions": [
                                {
                                    "competitors": [
                                        {"team": {"displayName": "United States"}},
                                        {"team": {"displayName": "Colombia"}}
                                    ]
                                }
                            ],
                            "id": "mock_event_999"
                        }
                    ]
                }
            elif "summary" in url:
                mock_resp.json.return_value = {
                    "rosters": [
                        {
                            "team": {"displayName": "United States"},
                            "roster": [
                                {"starter": True, "active": True, "athlete": {"displayName": f"US Player {i}"}}
                                for i in range(15)
                            ]
                        }
                    ]
                }
            else:
                mock_resp.status_code = 404
                mock_resp.json.return_value = {}
            return mock_resp

        self.mock_get.side_effect = mock_get_side_effect
        
        res = _fetch_team_recent_lineup("usa")
        self.assertEqual(len(res), 11)
        self.assertEqual(res[0], "us player 0")
        self.assertEqual(res[-1], "us player 10")

if __name__ == "__main__":
    unittest.main()
