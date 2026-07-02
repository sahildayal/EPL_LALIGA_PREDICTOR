import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestCornersScraper(unittest.TestCase):
    def setUp(self):
        self.cache_get_patcher = patch("src.data.cache.get", return_value=None)
        self.cache_set_patcher = patch("src.data.cache.set")
        self.mock_cache_get = self.cache_get_patcher.start()
        self.mock_cache_set = self.cache_set_patcher.start()

    def tearDown(self):
        self.cache_get_patcher.stop()
        self.cache_set_patcher.stop()

    @patch("requests.get")
    @patch("src.data.scrapers.fixtures._find_espn_event_id")
    def test_scrape_team_corners(self, mock_find, mock_get):
        # Mock recent completed event IDs (events in the past)
        mock_find.return_value = ("760487", "fifa.world")
        
        # Mock ESPN summary JSON with wonCorners statistic
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "boxscore": {
                "teams": [
                    {
                        "team": {"displayName": "Brazil"},
                        "statistics": [
                            {"name": "wonCorners", "displayValue": "6", "label": "Corner Kicks"}
                        ]
                    },
                    {
                        "team": {"displayName": "Japan"},
                        "statistics": [
                            {"name": "wonCorners", "displayValue": "4", "label": "Corner Kicks"}
                        ]
                    }
                ]
            }
        }
        mock_get.return_value = mock_resp

        from src.data.scrapers.corners import get_team_recent_corners
        res = get_team_recent_corners("brazil")
        self.assertEqual(res["won"], 6.0)
        self.assertEqual(res["conceded"], 4.0)

    @patch("requests.get")
    def test_cache_hit(self, mock_get):
        self.mock_cache_get.return_value = {"won": 7.0, "conceded": 3.0}
        from src.data.scrapers.corners import get_team_recent_corners
        res = get_team_recent_corners("brazil")
        self.assertEqual(res["won"], 7.0)
        self.assertEqual(res["conceded"], 3.0)
        mock_get.assert_not_called()

    @patch("requests.get")
    def test_scrape_fallback(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        from src.data.scrapers.corners import get_team_recent_corners
        res = get_team_recent_corners("brazil")
        self.assertEqual(res["won"], 5.0)
        self.assertEqual(res["conceded"], 5.0)

if __name__ == '__main__':
    unittest.main()
