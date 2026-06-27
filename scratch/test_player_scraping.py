import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import unittest
from src.data.scrapers.player_stats import get_player_stats

class TestPlayerScraping(unittest.TestCase):
    def test_seeded_player(self):
        stats = get_player_stats("Kylian Mbappe")
        self.assertEqual(stats["name"], "kylian mbappe")
        self.assertEqual(stats["position"], "FW")
        self.assertGreater(stats["goals_per_90"], 0.4)

    def test_scrape_fallback(self):
        # Test a non-seeded player to trigger scraping/defaults
        stats = get_player_stats("Declan Rice")
        self.assertIsNotNone(stats)
        self.assertIn("goals_per_90", stats)
        self.assertIn("assists_per_90", stats)

if __name__ == "__main__":
    unittest.main()
