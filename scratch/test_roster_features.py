import unittest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestRosterFeatures(unittest.TestCase):
    def test_roster_strength_calculations(self):
        from src.data.preprocessor import get_match_features
        features = get_match_features("brazil", "japan")
        # Verify extended feature length is 28 (original 25 + 3 new features)
        self.assertEqual(len(features), 28)
        self.assertTrue(features[25] > 0.0) # HTRosterStrength
        self.assertTrue(features[26] > 0.0) # ATRosterStrength

if __name__ == '__main__':
    unittest.main()
