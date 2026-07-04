from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch, MagicMock

# Import paper_trading to ensure it is in sys.modules and populated on src.market
import src.market.paper_trading

class TestBotBetting(unittest.TestCase):
    def setUp(self):
        # Patch external dependencies of run_predict to isolate the test
        self.predict_match_patcher = patch("main.predict_match")
        self.get_match_lineups_patcher = patch("main.get_match_lineups")
        self.fbref_patcher = patch("main.fbref")
        self.player_stats_patcher = patch("main.player_stats")
        self.calc_probs_patcher = patch("main.calculate_player_prop_probs")
        self.kalshi_client_patcher = patch("main.KalshiClient")
        
        # Patch the functions inside src.market.paper_trading directly
        self.get_summary_patcher = patch("src.market.paper_trading.get_personality_summary")
        self.update_bet_patcher = patch("src.market.paper_trading.update_bet")

        self.mock_predict_match = self.predict_match_patcher.start()
        self.mock_get_match_lineups = self.get_match_lineups_patcher.start()
        self.mock_fbref = self.fbref_patcher.start()
        self.mock_player_stats = self.player_stats_patcher.start()
        self.mock_calc_probs = self.calc_probs_patcher.start()
        self.mock_kalshi_client = self.kalshi_client_patcher.start()
        
        self.mock_get_summary = self.get_summary_patcher.start()
        self.mock_update_bet = self.update_bet_patcher.start()

        # Set up default mocks
        # predict_match mock
        mock_result = MagicMock()
        mock_result.probabilities = {"home_win": 0.33, "draw": 0.33, "away_win": 0.34}
        mock_result.model_breakdown = {}
        mock_result.sentiment = 0.0
        mock_result.elo_diff = 0.0
        mock_result.progression_probabilities = {"home_advances": 0.50, "away_advances": 0.50}
        self.mock_predict_match.return_value = mock_result

        # get_match_lineups mock (only Ronaldo on home team, empty away lineup)
        self.mock_get_match_lineups.return_value = {
            "home_lineup": ["Cristiano Ronaldo"],
            "away_lineup": [],
            "source": "mock_setup"
        }

        # fbref mock
        self.mock_fbref.get_team_data.return_value = {
            "avg_goals": 1.5,
            "avg_conceded": 1.0
        }

        # player_stats mock
        self.mock_player_stats.get_player_stats.return_value = {}

        # paper_trading mock
        self.mock_get_summary.side_effect = lambda port, name: {
            "bankroll": 1000.0,
            "active_bets": [],
            "recent_bets": []
        }
        self.mock_update_bet.return_value = {"action": "placed", "new": {"bet_type": "dummy", "stake": 0.0, "odds": 1.0}}

        # Kalshi markets mock
        self.mock_client_instance = MagicMock()
        self.mock_client_instance.get_soccer_markets.return_value = [
            {
                "event_title": "Portugal vs France",
                "markets": [
                    {"title": "Will Portugal win?", "yes_price": 0.33, "ticker": "KXWCGAME_PORTUGAL_WIN"},
                    {"title": "Will France win?", "yes_price": 0.34, "ticker": "KXWCGAME_FRANCE_WIN"},
                    {"title": "Will the game end in a draw?", "yes_price": 0.33, "ticker": "KXWCGAME_DRAW"},
                    {"title": "Will there be over 1.5 goals?", "yes_price": 0.80},
                    {"title": "Will there be over 2.5 goals?", "yes_price": 0.50},
                    {"title": "Will both teams score?", "yes_price": 0.60},
                    # Player props
                    {"title": "Cristiano Ronaldo: 1+ goals?", "yes_price": 0.40},
                    {"title": "Cristiano Ronaldo: 2+ goals?", "yes_price": 0.15},
                    {"title": "Cristiano Ronaldo: 1+ assists?", "yes_price": 0.25},
                    {"title": "Cristiano Ronaldo: 2+ assists?", "yes_price": 0.05},
                    {"title": "Cristiano Ronaldo: score or assist?", "yes_price": 0.55},
                ]
            }
        ]
        self.mock_kalshi_client.return_value = self.mock_client_instance

    def tearDown(self):
        self.predict_match_patcher.stop()
        self.get_match_lineups_patcher.stop()
        self.fbref_patcher.stop()
        self.player_stats_patcher.stop()
        self.calc_probs_patcher.stop()
        self.kalshi_client_patcher.stop()
        self.get_summary_patcher.stop()
        self.update_bet_patcher.stop()

    def run_prop_test(self, test_probs, expected_bet_type, expected_odds):
        self.mock_calc_probs.return_value = test_probs
        self.mock_update_bet.reset_mock()
        
        # Run main.run_predict
        from main import run_predict
        run_predict("Portugal vs France")

        print(f"\n[DEBUG: {expected_bet_type}] calls:")
        for call in self.mock_update_bet.call_args_list:
            print("  ", call)

        # Verify that athena placed a bet on the expected player prop market
        matched_call = False
        for call in self.mock_update_bet.call_args_list:
            args = call[0]
            if len(args) >= 7:
                port, name, home, away, bet_type, stake, odds = args[:7]
                if port == "predict" and name == "athena" and bet_type == expected_bet_type:
                    self.assertEqual(home, "portugal")
                    self.assertEqual(away, "france")
                    # Calculate expected Kelly stake
                    p_val = 0.05
                    if "1+ Goals" in expected_bet_type:
                        p_val = test_probs["goals_1"]
                    elif "2+ Goals" in expected_bet_type:
                        p_val = test_probs["goals_2"]
                    elif "1+ Assists" in expected_bet_type:
                        p_val = test_probs["assists_1"]
                    elif "2+ Assists" in expected_bet_type:
                        p_val = test_probs["assists_2"]
                    elif "Score or Assist" in expected_bet_type:
                        p_val = test_probs["goal_or_assist"]
                        
                    expected_b = expected_odds - 1.0
                    if expected_b > 0:
                        expected_f_star = (p_val * expected_b - (1.0 - p_val)) / expected_b
                        expected_fraction = max(0.02, min(0.15, 0.25 * expected_f_star))
                    else:
                        expected_fraction = 0.05
                    expected_stake = round(1000.0 * expected_fraction, 2)
                    self.assertAlmostEqual(stake, expected_stake, places=2)
                    self.assertAlmostEqual(odds, expected_odds, places=4)
                    matched_call = True
                    break
        
        self.assertTrue(matched_call, f"Expected update_bet call for {expected_bet_type} not found")

    def test_player_prop_goals_1(self):
        probs = {
            "goals_1": 0.80, "goals_2": 0.15,
            "assists_1": 0.25, "assists_2": 0.05,
            "goal_or_assist": 0.55
        }
        self.run_prop_test(probs, "Player Props - Cristiano Ronaldo 1+ Goals", 2.5)

    def test_player_prop_goals_2(self):
        probs = {
            "goals_1": 0.40, "goals_2": 0.55,
            "assists_1": 0.25, "assists_2": 0.05,
            "goal_or_assist": 0.55
        }
        self.run_prop_test(probs, "Player Props - Cristiano Ronaldo 2+ Goals", 1.0 / 0.15)

    def test_player_prop_assists_1(self):
        probs = {
            "goals_1": 0.40, "goals_2": 0.15,
            "assists_1": 0.65, "assists_2": 0.05,
            "goal_or_assist": 0.55
        }
        self.run_prop_test(probs, "Player Props - Cristiano Ronaldo 1+ Assists", 4.0)

    def test_player_prop_assists_2(self):
        probs = {
            "goals_1": 0.40, "goals_2": 0.15,
            "assists_1": 0.25, "assists_2": 0.45,
            "goal_or_assist": 0.55
        }
        self.run_prop_test(probs, "Player Props - Cristiano Ronaldo 2+ Assists", 20.0)

    def test_player_prop_goal_or_assist(self):
        probs = {
            "goals_1": 0.40, "goals_2": 0.15,
            "assists_1": 0.25, "assists_2": 0.05,
            "goal_or_assist": 0.95
        }
        self.run_prop_test(probs, "Player Props - Cristiano Ronaldo Score or Assist", 1.0 / 0.55)

if __name__ == "__main__":
    unittest.main()
