import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import unittest
import pandas as pd
from unittest.mock import patch, MagicMock
from src.data.scrapers.fbref import compute_dynamic_team_stats
from src.market.paper_trading import _update_player_stats_from_completed_match

class TestDynamicUpdates(unittest.TestCase):

    @patch("pandas.read_csv")
    @patch("pathlib.Path.exists")
    def test_compute_dynamic_team_stats(self, mock_exists, mock_read_csv):
        mock_exists.return_value = True
        
        # Mock master dataset with 5 recent games for Portugal
        mock_df = pd.DataFrame([
            {"HomeTeam": "portugal", "AwayTeam": "france", "FTHG": 2, "FTAG": 1, "FTR": "H", "Date": "2026-06-25"},
            {"HomeTeam": "germany", "AwayTeam": "portugal", "FTHG": 1, "FTAG": 3, "FTR": "A", "Date": "2026-06-21"},
            {"HomeTeam": "portugal", "AwayTeam": "spain", "FTHG": 1, "FTAG": 1, "FTR": "D", "Date": "2026-06-18"},
            {"HomeTeam": "morocco", "AwayTeam": "portugal", "FTHG": 0, "FTAG": 2, "FTR": "A", "Date": "2026-06-14"},
            {"HomeTeam": "portugal", "AwayTeam": "croatia", "FTHG": 0, "FTAG": 1, "FTR": "A", "Date": "2026-06-11"}
        ])
        mock_read_csv.return_value = mock_df
        
        stats = compute_dynamic_team_stats("portugal")
        
        # Portugal goals: 2 (H) + 3 (A) + 1 (H) + 2 (A) + 0 (H) = 8 goals in 5 games -> 1.6 avg_goals
        # Portugal conceded: 1 (H) + 1 (A) + 1 (H) + 0 (A) + 1 (H) = 4 goals in 5 games -> 0.8 avg_conceded
        # Points: 3 (W) + 3 (W) + 1 (D) + 3 (W) + 0 (L) = 10 pts. Max possible: 3 * 5 = 15. Form: 10/15 = 0.667
        self.assertEqual(stats["avg_goals"], 1.6)
        self.assertEqual(stats["avg_conceded"], 0.8)
        self.assertAlmostEqual(stats["form"], 0.667, places=3)
        self.assertIn("Dynamic master_dataset", stats["data_sources"][0])

    @patch("src.data.scrapers.fixtures._fetch_espn_event_lineup")
    @patch("src.data.scrapers.player_stats.get_player_stats")
    @patch("src.data.cache.save_player_stats")
    def test_update_player_stats_from_completed_match(self, mock_save, mock_get, mock_fetch_lineup):
        # Roster lineups mock
        mock_fetch_lineup.return_value = {
            "home_lineup": ["Cristiano Ronaldo"],
            "away_lineup": []
        }
        
        # Current cached stats for Cristiano Ronaldo
        mock_get.return_value = {
            "position": "FW",
            "goals_per_90": 0.50,
            "assists_per_90": 0.20,
            "xg_per_90": 0.40,
            "club_team": "al nassr",
            "intl_team": "portugal"
        }
        
        match_stats = {
            "goals": {"cristiano ronaldo": 1},
            "assists": {}
        }
        
        _update_player_stats_from_completed_match("portugal", "france", match_stats, "event-123", "fifa.world")
        
        # We expect a save_player_stats call for Cristiano Ronaldo
        # Expected new values:
        # goals: (0.5 * 10 + 1) / 11 = 6.0 / 11 = 0.545
        # assists: (0.2 * 10 + 0) / 11 = 2.0 / 11 = 0.182
        # xg: (0.4 * 10 + 1.0) / 11 = 5.0 / 11 = 0.455
        mock_save.assert_called_once_with(
            "cristiano ronaldo", "FW", 0.455, 0.545, 0.182, "al nassr", "portugal"
        )

if __name__ == "__main__":
    unittest.main()
