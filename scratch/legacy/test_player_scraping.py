import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch, MagicMock
from src.data.scrapers.player_stats import get_player_stats

class TestPlayerScraping(unittest.TestCase):
    @patch("src.data.scrapers.player_stats.requests.get")
    def test_seeded_player(self, mock_get):
        stats = get_player_stats("Kylian Mbappe")
        self.assertEqual(stats["name"], "kylian mbappe")
        self.assertEqual(stats["position"], "FW")
        self.assertGreater(stats["goals_per_90"], 0.4)
        mock_get.assert_not_called()

    @patch("src.data.scrapers.player_stats.requests.get")
    def test_scrape_fallback(self, mock_get):
        # Clear cache first to force a scraping path
        from src.data.cache import _conn
        conn = _conn()
        try:
            with conn:
                conn.execute("DELETE FROM player_statistics WHERE player_name = ?", ("declan rice",))
        finally:
            conn.close()

        # Set up mock response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://fbref.com/en/players/abc1234/Declan-Rice"
        mock_resp.text = """
        <html>
        <body>
            <strong>Position</strong>: MF (CM)
            <table id="stats_standard_90_etc">
                <tbody>
                    <tr>
                        <td data-stat="xg_per90">0.15</td>
                        <td data-stat="goals_per90">0.10</td>
                        <td data-stat="assists_per90">0.05</td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        mock_get.return_value = mock_resp

        # Test a non-seeded player to trigger scraping/defaults
        stats = get_player_stats("Declan Rice")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["name"], "declan rice")
        self.assertEqual(stats["position"], "CM")
        self.assertEqual(stats["source"], "scraped_blend")
        self.assertIn("goals_per_90", stats)
        self.assertIn("assists_per_90", stats)

        # Call again to test cache hit & verify source tag is cached_sqlite
        stats_cached = get_player_stats("Declan Rice")
        self.assertEqual(stats_cached["source"], "cached_sqlite")
        self.assertEqual(stats_cached["position"], "CM")

if __name__ == "__main__":
    unittest.main()
