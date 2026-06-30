import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestRosterHealth(unittest.TestCase):
    def test_injury_news_scoring(self):
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
