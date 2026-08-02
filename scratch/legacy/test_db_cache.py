from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
import unittest
import time
from src.data.cache import save_player_stats, get_player_stats_cache

class TestDbCache(unittest.TestCase):
    def test_save_and_retrieve_stats(self):
        save_player_stats("Joao Neves", "CM", 0.12, 0.10, 0.22, "PSG", "Portugal")
        stats = get_player_stats_cache("Joao Neves")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["position"], "CM")
        self.assertEqual(stats["goals_per_90"], 0.10)
        self.assertEqual(stats["assists_per_90"], 0.22)
        self.assertEqual(stats["club_team"], "psg")
        self.assertEqual(stats["intl_team"], "portugal")
        
    def test_missing_stats(self):
        self.assertIsNone(get_player_stats_cache("Non Existent Player"))

    def test_expiration(self):
        # Save a player
        save_player_stats("Expired Player", "ST", 0.5, 0.4, 0.1, "FCB", "France")
        # Verify it exists
        self.assertIsNotNone(get_player_stats_cache("Expired Player"))
        
        # Manually update last_updated in the database to be older than 7 days
        import sqlite3
        from src.data.cache import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        try:
            with conn:
                conn.execute(
                    "UPDATE player_statistics SET last_updated = ? WHERE player_name = ?",
                    (time.time() - 604800 - 10, "expired player")
                )
        finally:
            conn.close()
        
        # Verify that it is now considered expired and returns None
        self.assertIsNone(get_player_stats_cache("Expired Player"))

    def test_purge_expired(self):
        from src.data.cache import purge_expired, DB_PATH
        # Save a player statistics entry
        save_player_stats("Purge Player", "ST", 0.5, 0.4, 0.1, "FCB", "France")
        
        # Manually update last_updated in the database to be older than 7 days
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        try:
            with conn:
                conn.execute(
                    "UPDATE player_statistics SET last_updated = ? WHERE player_name = ?",
                    (time.time() - 604800 - 10, "purge player")
                )
        finally:
            conn.close()
            
        # Verify it is in the database using raw query
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                "SELECT player_name FROM player_statistics WHERE player_name = ?",
                ("purge player",)
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            conn.close()

        # Call purge_expired
        purge_expired()

        # Verify it has been deleted from the database
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                "SELECT player_name FROM player_statistics WHERE player_name = ?",
                ("purge player",)
            ).fetchone()
            self.assertIsNone(row)
        finally:
            conn.close()

if __name__ == "__main__":
    unittest.main()
