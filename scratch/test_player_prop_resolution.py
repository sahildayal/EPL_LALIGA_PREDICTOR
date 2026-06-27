import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import unittest
from unittest.mock import patch, MagicMock
from src.market.paper_trading import _check_bet_win, resolve_pending_bets, load_state, save_state

class TestPlayerPropResolution(unittest.TestCase):

    def test_check_bet_win_goals(self):
        # Match stats containing 1 goal for Cristiano Ronaldo
        stats = {
            "goals": {"cristiano ronaldo": 1},
            "assists": {}
        }
        
        # 1+ goals should be True
        self.assertTrue(_check_bet_win("Player Goals - Cristiano Ronaldo 1+ Goals", "portugal", "france", 1, 0, stats))
        # 2+ goals should be False
        self.assertFalse(_check_bet_win("Player Goals - Cristiano Ronaldo 2+ Goals", "portugal", "france", 1, 0, stats))
        # 1+ assists should be False
        self.assertFalse(_check_bet_win("Player Assists - Cristiano Ronaldo 1+ Assists", "portugal", "france", 1, 0, stats))
        # Score or assist should be True
        self.assertTrue(_check_bet_win("Player Props - Cristiano Ronaldo Score or Assist", "portugal", "france", 1, 0, stats))

    def test_check_bet_win_assists(self):
        # Match stats containing 2 assists for Bruno Fernandes
        stats = {
            "goals": {},
            "assists": {"bruno fernandes": 2}
        }
        
        # 1+ assists should be True
        self.assertTrue(_check_bet_win("Player Assists - Bruno Fernandes 1+ Assists", "portugal", "france", 0, 2, stats))
        # 2+ assists should be True
        self.assertTrue(_check_bet_win("Player Assists - Bruno Fernandes 2+ Assists", "portugal", "france", 0, 2, stats))
        # 1+ goals should be False
        self.assertFalse(_check_bet_win("Player Goals - Bruno Fernandes 1+ Goals", "portugal", "france", 0, 2, stats))
        # Score or assist should be True
        self.assertTrue(_check_bet_win("Player Props - Bruno Fernandes Score or Assist", "portugal", "france", 0, 2, stats))

    @patch("src.market.paper_trading._fetch_completed_match_stats")
    @patch("src.market.paper_trading.load_state")
    @patch("src.market.paper_trading.save_state")
    def test_resolve_pending_bets_player_props(self, mock_save, mock_load, mock_fetch):
        # Mock completed match stats from ESPN
        mock_fetch.return_value = {
            "goals": {"kylian mbappe": 2},
            "assists": {"antoine griezmann": 1}
        }
        
        # Mock active bets state
        mock_state = {
            "predict": {
                "big_d": {
                    "bankroll": 1000.0,
                    "active_bets": [
                        {
                            "home": "france",
                            "away": "poland",
                            "bet_type": "Player Props - Kylian Mbappe 2+ Goals",
                            "stake": 100.0,
                            "odds": 3.5
                        },
                        {
                            "home": "france",
                            "away": "poland",
                            "bet_type": "Player Props - Antoine Griezmann 2+ Assists",
                            "stake": 50.0,
                            "odds": 5.0
                        }
                    ],
                    "history": []
                },
                "sigmaballs": {
                    "bankroll": 1000.0,
                    "active_bets": [],
                    "history": []
                }
            }
        }
        mock_load.return_value = mock_state
        
        # Resolve match: France vs Poland (2 - 0)
        results = resolve_pending_bets("france", "poland", 2, 0)
        
        # We expect two resolved bets in results
        self.assertEqual(len(results), 2)
        
        # Find results
        res_mbappe = next(r[2] for r in results if "Kylian Mbappe" in r[2]["bet_type"])
        res_griezmann = next(r[2] for r in results if "Antoine Griezmann" in r[2]["bet_type"])
        
        # Mbappe won (2 goals scored >= 2)
        self.assertEqual(res_mbappe["result"], "WIN")
        self.assertAlmostEqual(res_mbappe["pnl"], 250.0) # 100 * 3.5 - 100 = 250
        
        # Griezmann lost (1 assist scored < 2)
        self.assertEqual(res_griezmann["result"], "LOSS")
        self.assertAlmostEqual(res_griezmann["pnl"], -50.0)

if __name__ == "__main__":
    unittest.main()
