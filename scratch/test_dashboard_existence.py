import unittest
import os
from pathlib import Path

class TestDashboardExistence(unittest.TestCase):
    def test_dashboard_file_exists(self):
        # The dashboard.html should be in the project root
        project_root = Path(__file__).resolve().parents[1]
        dashboard_path = project_root / "dashboard.html"
        self.assertTrue(dashboard_path.exists(), "dashboard.html does not exist in the project root")
        
        # Read the file content
        with open(dashboard_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Assert critical elements exist in the html
        self.assertIn('id="bracket-tree"', content, "dashboard.html is missing an element with id='bracket-tree'")
        self.assertIn('id="prob-table"', content, "dashboard.html is missing an element with id='prob-table'")
        self.assertIn('simulation_results.json', content, "dashboard.html should reference 'simulation_results.json'")
        self.assertIn('🏆 2026 World Cup Monte Carlo Dashboard', content, "dashboard.html is missing the header text")

if __name__ == "__main__":
    unittest.main()
