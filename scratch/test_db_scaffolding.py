import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.data.cache import save_team_travel, get_team_last_travel, _conn

class TestDbScaffolding(unittest.TestCase):
    def test_travel_caching(self):
        save_team_travel("portugal", "lisbon", "2026-06-28", 38.72, -9.14)
        last_travel = get_team_last_travel("portugal")
        self.assertEqual(last_travel["city"], "lisbon")
        self.assertEqual(last_travel["lat"], 38.72)

if __name__ == "__main__":
    unittest.main()
