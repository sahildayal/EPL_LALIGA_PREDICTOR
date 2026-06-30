import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestRosterHealth(unittest.TestCase):
    def setUp(self):
        # Prevent database caching from polluting unit tests
        self.cache_get_patcher = patch("src.data.cache.get", return_value=None)
        self.cache_set_patcher = patch("src.data.cache.set")
        self.mock_cache_get = self.cache_get_patcher.start()
        self.mock_cache_set = self.cache_set_patcher.start()

    def tearDown(self):
        self.cache_get_patcher.stop()
        self.cache_set_patcher.stop()

    @patch("src.data.preprocessor.fbref.get_team_data")
    @patch("src.data.preprocessor.news.get_sentiment")
    @patch("src.data.preprocessor.search_wc_fixture")
    @patch("src.data.scrapers.fixtures.get_match_lineups")
    @patch("src.data.scrapers.player_stats.get_player_stats")
    @patch("src.data.scrapers.news.get_roster_health")
    def test_injury_news_scoring(self, mock_health, mock_stats, mock_lineups, mock_fixture, mock_sentiment, mock_team):
        # Set up mocks to avoid network calls
        mock_team.return_value = {"avg_goals": 1.4, "avg_conceded": 1.1, "form": 0.6}
        mock_sentiment.return_value = {"score": 0.0}
        mock_fixture.return_value = None
        mock_lineups.return_value = {"home_lineup": ["player1"], "away_lineup": ["player2"]}
        mock_stats.return_value = {"xg_per_90": 0.5}
        mock_health.return_value = 1.0

        from src.data.preprocessor import get_match_features
        features = get_match_features("brazil", "japan")
        # Roster health features appended: len is 31
        self.assertEqual(len(features), 31)
        self.assertTrue(features[28] <= 1.0) # HTRosterHealth
        self.assertTrue(features[29] <= 1.0) # ATRosterHealth

    @patch('requests.get')
    def test_get_roster_health_no_injuries(self, mock_get):
        from src.data.scrapers.news import get_roster_health
        
        # Mock XML response with no injury headlines
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
        <channel>
            <item><title>Neymar shines in Brazil training</title></item>
            <item><title>Vinicius Junior scores a hat-trick</title></item>
        </channel>
        </rss>
        """
        mock_get.return_object = mock_resp
        mock_get.return_value = mock_resp
        
        roster = ["Neymar", "Vinicius Junior", "Alisson"]
        health = get_roster_health("Brazil", roster)
        # Expected health: 1.0 (no players flagged with injury keywords)
        self.assertEqual(health, 1.0)

    @patch('requests.get')
    def test_get_roster_health_with_injuries(self, mock_get):
        from src.data.scrapers.news import get_roster_health
        
        # Mock XML response containing injury keywords for Neymar and Alisson
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
        <channel>
            <item><title>Neymar out with a hamstring injury</title></item>
            <item><title>Vinicius Junior is fit and ready</title></item>
            <item><title>Alisson doubtful for the next match after knee pain</title></item>
        </channel>
        </rss>
        """
        mock_get.return_value = mock_resp
        
        roster = ["Neymar", "Vinicius Junior", "Alisson"]
        health = get_roster_health("Brazil", roster)
        # 2 out of 11 (max default is 11) flagged:
        # health = 1.0 - (2 / 11) = 1.0 - 0.1818 = 0.8181...
        # self.assertTrue(0.81 <= health <= 0.82)
        # Let's check calculation exactly:
        self.assertAlmostEqual(health, 1.0 - (2 / 11), places=4)

    @patch('requests.get')
    def test_get_roster_health_request_failure(self, mock_get):
        from src.data.scrapers.news import get_roster_health
        
        # Mock connection error/status code not 200
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        
        roster = ["Neymar"]
        health = get_roster_health("Brazil", roster)
        # Expected: 1.0 on network failure
        self.assertEqual(health, 1.0)

if __name__ == '__main__':
    unittest.main()
