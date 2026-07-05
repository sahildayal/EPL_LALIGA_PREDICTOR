import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import run_daily

class TestRunDaily(unittest.TestCase):
    @patch("main.run_predict")
    @patch("main.run_ask")
    @patch("main.run_parlay")
    @patch("json.load")
    @patch("os.path.exists", return_value=True)
    @patch("src.models.simulation.run_tournament_simulation")
    @patch("builtins.open", new_callable=mock_open)
    def test_run_daily_matches(self, mock_file, mock_sim, mock_exists, mock_json, mock_parlay, mock_ask, mock_predict):
        from datetime import datetime, timezone
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mock_json.return_value = [
            {"home": "france", "away": "sweden", "date": f"{today_str}T18:00:00Z"}
        ]
        mock_sim.return_value = {"probabilities": []}
        
        run_daily()
        
        mock_file.assert_any_call(os.path.join("data", "processed", "daily_schedule.json"), "r")
        mock_file.assert_any_call(os.path.join("data", "processed", "simulation_results.json"), "w")
        mock_predict.assert_called_once_with("france vs sweden")
        mock_ask.assert_called_once_with("france vs sweden", "Gemini 2.5 Flash")
        
        # Verify parlay engine calls
        self.assertEqual(mock_parlay.call_count, 2)
        mock_parlay.assert_any_call(longshot=False, today_only=True)
        mock_parlay.assert_any_call(longshot=True, today_only=True)

    @patch("main.run_predict")
    @patch("main.run_ask")
    @patch("main.run_parlay")
    @patch("json.load")
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open)
    def test_run_daily_no_matches(self, mock_file, mock_exists, mock_json, mock_parlay, mock_ask, mock_predict):
        from datetime import datetime, timezone
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mock_json.return_value = []
        
        run_daily()
        
        mock_file.assert_called_once_with(os.path.join("data", "processed", "daily_schedule.json"), "r")
        mock_predict.assert_not_called()
        mock_ask.assert_not_called()
        mock_parlay.assert_not_called()

    @patch("main.run_predict")
    @patch("main.run_ask")
    @patch("main.run_parlay")
    @patch("json.load")
    @patch("os.path.exists", return_value=True)
    @patch("src.models.simulation.run_tournament_simulation")
    @patch("builtins.open", new_callable=mock_open)
    def test_run_daily_early_tomorrow_match(self, mock_file, mock_sim, mock_exists, mock_json, mock_parlay, mock_ask, mock_predict):
        from datetime import datetime, timedelta, timezone
        today_utc = datetime.now(timezone.utc).date()
        early_tomorrow_dt = datetime.combine(today_utc + timedelta(days=1), datetime.min.time().replace(hour=2))
        early_tomorrow_str = early_tomorrow_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        mock_json.return_value = [
            {"home": "mexico", "away": "england", "date": early_tomorrow_str}
        ]
        mock_sim.return_value = {"probabilities": []}
        
        run_daily()
        
        # Should call predict on Mexico vs England
        mock_predict.assert_called_once_with("mexico vs england")
        mock_ask.assert_called_once_with("mexico vs england", "Gemini 2.5 Flash")

if __name__ == '__main__':
    unittest.main()

