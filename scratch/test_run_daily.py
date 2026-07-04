import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

class TestRunDaily(unittest.TestCase):
    @patch("main.run_predict")
    @patch("main.run_ask")
    @patch("main.run_parlay")
    @patch("json.load")
    @patch("os.path.exists", return_value=True)
    def test_run_daily_matches(self, mock_exists, mock_json, mock_parlay, mock_ask, mock_predict):
        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        mock_json.return_value = [
            {"home": "france", "away": "sweden", "date": f"{today_str}T18:00:00Z"}
        ]
        
        from main import run_daily
        run_daily()
        
        mock_predict.assert_called_once_with("france vs sweden")
        mock_ask.assert_called_once_with("france vs sweden", "Gemini 2.5 Flash")
        
        # Verify parlay engine calls
        self.assertEqual(mock_parlay.call_count, 2)
        mock_parlay.assert_any_call(longshot=False, today_only=True)
        mock_parlay.assert_any_call(longshot=True, today_only=True)

if __name__ == '__main__':
    unittest.main()
