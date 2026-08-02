import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestRosterFeatures(unittest.TestCase):
    @patch("src.data.preprocessor.fbref.get_team_data")
    @patch("src.data.preprocessor.news.get_sentiment")
    @patch("src.data.preprocessor.search_wc_fixture")
    @patch("src.data.scrapers.fixtures.get_match_lineups")
    @patch("src.data.scrapers.player_stats.get_player_stats")
    @patch("src.data.scrapers.news.get_roster_health")
    def test_roster_strength_calculations(self, mock_health, mock_stats, mock_lineups, mock_fixture, mock_sentiment, mock_team):
        # Set up mocks to avoid network calls
        mock_team.return_value = {"avg_goals": 1.4, "avg_conceded": 1.1, "form": 0.6}
        mock_sentiment.return_value = {"score": 0.0}
        mock_fixture.return_value = None
        mock_lineups.return_value = {"home_lineup": ["player1"], "away_lineup": ["player2"]}
        mock_stats.return_value = {"xg_per_90": 0.5}
        mock_health.return_value = 1.0

        from src.data.preprocessor import get_match_features
        features = get_match_features("brazil", "japan")
        # Verify extended feature length is 31 (original 25 + 3 strength + 3 health features)
        self.assertEqual(len(features), 31)
        self.assertTrue(features[25] > 0.0) # HTRosterStrength
        self.assertTrue(features[26] > 0.0) # ATRosterStrength

if __name__ == '__main__':
    unittest.main()
