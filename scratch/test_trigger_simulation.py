import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
import json
import pandas as pd
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import run_daily, run_update

class TestTriggerSimulation(unittest.TestCase):
    @patch("main.run_predict")
    @patch("main.run_ask")
    @patch("main.run_parlay")
    @patch("src.models.simulation.run_tournament_simulation")
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_run_daily_triggers_simulation(self, mock_file_open, mock_exists, mock_sim, mock_parlay, mock_ask, mock_predict):
        # Setup mocks
        mock_exists.side_effect = lambda path: "daily_schedule.json" in str(path)
        
        from datetime import datetime, timezone
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        schedule_data = [{"home": "france", "away": "sweden", "date": f"{today_str}T18:00:00Z"}]
        mock_sim.return_value = {"probabilities": [{"team": "france", "champion": 0.5}]}
        
        # We need mock_open to handle daily_schedule.json (read) and simulation_results.json (write)
        read_handle = mock_open(read_data=json.dumps(schedule_data))()
        
        write_handle = MagicMock()
        write_handle.__enter__.return_value = write_handle
        
        def open_side_effect(file, mode="r", *args, **kwargs):
            if "daily_schedule.json" in str(file) and "r" in mode:
                return read_handle
            elif "simulation_results.json" in str(file) and "w" in mode:
                return write_handle
            raise FileNotFoundError(f"Mock open not configured for: {file} ({mode})")
            
        mock_file_open.side_effect = open_side_effect
        
        # Execute run_daily
        run_daily()
        
        # Assert simulation was called
        mock_sim.assert_called_once_with(num_runs=10000)
        
        # Assert results were written to the expected path
        mock_file_open.assert_any_call(os.path.join("data", "processed", "simulation_results.json"), "w")
        
        # Assert that the written content contains the simulation results
        write_calls = write_handle.write.call_args_list
        written_content = "".join(call[0][0] for call in write_calls)
        written_json = json.loads(written_content)
        self.assertEqual(written_json.get("probabilities"), [{"team": "france", "champion": 0.5}])

    @patch("requests.get")
    @patch("src.models.trainer.initialize_master_dataset")
    @patch("pandas.read_csv")
    @patch("src.models.trainer.train_and_save_all")
    @patch("src.data.scrapers.upcoming_and_stats.scrape_upcoming_fixtures")
    @patch("src.data.scrapers.upcoming_and_stats.scrape_tournament_stats")
    @patch("src.models.simulation.run_tournament_simulation")
    @patch("builtins.open")
    def test_run_update_triggers_simulation(self, mock_file_open, mock_sim, mock_stats, mock_fixtures, mock_train, mock_read_csv, mock_init, mock_get):
        # Mock requests.get to return a completed match that is already in master dataset
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "events": [
                {
                    "status": {"type": {"completed": True}},
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "France"}, "score": "2"},
                                {"homeAway": "away", "team": {"displayName": "Sweden"}, "score": "1"}
                            ]
                        }
                    ],
                    "date": "2026-07-05T18:00:00Z"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Mock master dataset to have the match so exists is True
        mock_df = pd.DataFrame([
            {"HomeTeam": "france", "AwayTeam": "sweden", "FTHG": 2, "FTAG": 1, "FTR": "H", "Date": "2026-07-05"}
        ])
        mock_read_csv.return_value = mock_df
        
        mock_sim.return_value = {"probabilities": [{"team": "argentina", "champion": 0.6}]}
        
        write_handle = MagicMock()
        write_handle.__enter__.return_value = write_handle
        
        def open_side_effect(file, mode="r", *args, **kwargs):
            if "simulation_results.json" in str(file) and "w" in mode:
                return write_handle
            raise FileNotFoundError(f"Mock open not configured for: {file} ({mode})")
            
        mock_file_open.side_effect = open_side_effect
        
        # Execute run_update
        run_update()
        
        # Assert simulation was called
        mock_sim.assert_called_once_with(num_runs=10000)
        
        # Assert results were written to the expected path
        mock_file_open.assert_any_call(os.path.join("data", "processed", "simulation_results.json"), "w")
        
        # Assert that the written content contains the simulation results
        write_calls = write_handle.write.call_args_list
        written_content = "".join(call[0][0] for call in write_calls)
        written_json = json.loads(written_content)
        self.assertEqual(written_json.get("probabilities"), [{"team": "argentina", "champion": 0.6}])

if __name__ == "__main__":
    unittest.main()
