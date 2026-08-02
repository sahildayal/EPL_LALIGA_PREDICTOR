import unittest
import sys
import os
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import src.data.cache as cache
from src.data.cache import save_team_travel, get_team_last_travel

class TestDbScaffolding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_db_path = cache.DB_PATH
        cls.orig_db_init = cache._db_initialized
        cls.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.temp_db.close()
        cache.DB_PATH = Path(cls.temp_db.name)
        cache._db_initialized = False

    @classmethod
    def tearDownClass(cls):
        cache.DB_PATH = cls.orig_db_path
        cache._db_initialized = cls.orig_db_init
        try:
            os.remove(cls.temp_db.name)
        except Exception:
            pass

    def test_travel_caching(self):
        save_team_travel("portugal", "lisbon", "2026-06-28", 38.72, -9.14)
        last_travel = get_team_last_travel("portugal", "2026-06-29")
        self.assertIsNotNone(last_travel)
        self.assertEqual(last_travel["city"], "lisbon")
        self.assertEqual(last_travel["lat"], 38.72)

if __name__ == "__main__":
    unittest.main()
