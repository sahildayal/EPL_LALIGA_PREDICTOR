import unittest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1]))
import src.data.cache as cache
from src.data.preprocessor import calculate_distance_km, get_match_features, FEATURE_NAMES
from src.data.cache import save_team_travel

class TestFatigueTravel(unittest.TestCase):
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
    def test_haversine_distance(self):
        # Distance between London (51.5, -0.1) and Paris (48.8, 2.3)
        dist = calculate_distance_km(51.5, -0.1, 48.8, 2.3)
        self.assertTrue(300 < dist < 400)

    @patch("src.data.preprocessor.search_wc_fixture")
    def test_get_match_features_with_travel_cache(self, mock_search):
        # Setup mock fixture
        mock_search.return_value = {
            "date": "2026-06-28T15:00Z",
            "venue": "Munich Football Arena"  # Munich: 48.1351, 11.5820
        }
        
        # Save team last travel log
        # Portugal: Lisbon (38.7223, -9.1393) on 2026-06-25 (3 days before 2026-06-28)
        save_team_travel("portugal", "lisbon", "2026-06-25", 38.7223, -9.1393)
        # France: Paris (48.8566, 2.3522) on 2026-06-22 (6 days before 2026-06-28)
        save_team_travel("france", "paris", "2026-06-22", 48.8566, 2.3522)
        
        # Run features preprocessor
        features = get_match_features("portugal", "france")
        
        # Verify length is 25 (17 base + 8 new)
        self.assertEqual(len(features), 25)
        
        # Map feature values
        feat_dict = dict(zip(FEATURE_NAMES, features))
        
        # Assert rest days and fatigue
        self.assertEqual(feat_dict["HTRestDays"], 3.0)
        self.assertEqual(feat_dict["ATRestDays"], 6.0)
        self.assertEqual(feat_dict["RestDisparity"], -3.0)
        self.assertEqual(feat_dict["HTExtremeFatigue"], 1.0)
        self.assertEqual(feat_dict["ATExtremeFatigue"], 0.0)
        
        # Assert travel distance (Lisbon to Munich is ~1960 km, Paris to Munich is ~680 km)
        self.assertTrue(1900 < feat_dict["HTTravel"] < 2050)
        self.assertTrue(600 < feat_dict["ATTravel"] < 750)
        self.assertAlmostEqual(feat_dict["TravelDisparity"], feat_dict["HTTravel"] - feat_dict["ATTravel"], places=2)

if __name__ == "__main__":
    unittest.main()
