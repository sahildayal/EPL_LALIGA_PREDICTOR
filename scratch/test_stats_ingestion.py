import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestStatsIngestion(unittest.TestCase):
    @patch("requests.get")
    def test_scrape_tournament_stats(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "stats": [
                {
                    "name": "goalsLeaders",
                    "leaders": [
                        {"athlete": {"displayName": "Kylian Mbappe", "team": {"displayName": "France"}}, "value": 6.0}
                    ]
                },
                {
                    "name": "assistsLeaders",
                    "leaders": [
                        {"athlete": {"displayName": "Lionel Messi", "team": {"displayName": "Argentina"}}, "value": 3.0}
                    ]
                }
            ]
        }
        mock_get.return_value = mock_resp
        
        from src.data.scrapers.upcoming_and_stats import scrape_tournament_stats
        res = scrape_tournament_stats()
        self.assertEqual(res["goals"]["kylian mbappe"], 6.0)
        self.assertEqual(res["assists"]["lionel messi"], 3.0)

    @patch("requests.get")
    def test_scrape_upcoming_fixtures(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "events": [
                {
                    "date": "2026-07-04T18:00Z",
                    "status": {"type": {"completed": False}},
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "Argentina"}},
                                {"homeAway": "away", "team": {"displayName": "Brazil"}}
                            ]
                        }
                    ]
                },
                {
                    "date": "2026-07-04T21:00Z",
                    "status": {"type": {"completed": True}},
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "France"}},
                                {"homeAway": "away", "team": {"displayName": "England"}}
                            ]
                        }
                    ]
                }
            ]
        }
        mock_get.return_value = mock_resp
        
        from src.data.scrapers.upcoming_and_stats import scrape_upcoming_fixtures
        res = scrape_upcoming_fixtures()
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0]["home"], "argentina")
        self.assertEqual(res[0]["away"], "brazil")
        self.assertEqual(res[0]["date"], "2026-07-04T18:00Z")

if __name__ == '__main__':
    unittest.main()
