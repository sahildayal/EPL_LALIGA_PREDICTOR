import unittest
from unittest.mock import patch, MagicMock
import os
import json
from src.market.llm import fetch_team_news_bullets, run_news_debate

class TestNewsDebates(unittest.TestCase):
    @patch('src.market.llm.search_web')
    def test_fetch_team_news_bullets(self, mock_search):
        mock_search.return_value = {
            "summary": "France team news: Mbappe is fit. Kante returns to training. Saliba is resting.",
            "citations": ["http://espn.com/news"]
        }
        bullets = fetch_team_news_bullets("France")
        self.assertIn("Mbappe", bullets)
        self.assertIn("Kante", bullets)

    @patch('src.market.llm.fetch_team_news_bullets')
    @patch('src.market.llm.generate_debate')
    def test_run_news_debate_saves_json(self, mock_generate_debate, mock_bullets):
        mock_bullets.side_effect = lambda team: f"Mock bullets for {team}"
        
        # Mock the debate result
        mock_generate_debate.return_value = {
            "magnus": "Magnus take",
            "athena": "Athena take",
            "consensus": "Consensus take",
            "personal_bets": {"magnus": {}, "athena": {}}
        }
        
        # Call run_news_debate
        home = "france"
        away = "sweden"
        probs = {"home_win": 0.6, "draw": 0.2, "away_win": 0.2}
        elo_diff = 120.0
        sentiment = 0.1
        news_flags = []
        target_bets = []
        
        # Run it
        res = run_news_debate(
            home=home,
            away=away,
            probs=probs,
            elo_diff=elo_diff,
            sentiment=sentiment,
            news_flags=news_flags,
            target_bets=target_bets
        )
        
        # Verify JSON file is written to data/processed/debates/
        from datetime import datetime, timezone
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        expected_path = f"data/processed/debates/{date_str}-france-vs-sweden.json"
        
        self.assertTrue(os.path.exists(expected_path))
        with open(expected_path, "r") as f:
            saved_data = json.load(f)
        
        self.assertEqual(saved_data["home"], "france")
        self.assertEqual(saved_data["away"], "sweden")
        self.assertEqual(saved_data["debate"]["magnus"], "Magnus take")
        self.assertIn("Mock bullets for france", saved_data["home_news_bullets"])
        self.assertIn("Mock bullets for sweden", saved_data["away_news_bullets"])
        
        # Clean up
        if os.path.exists(expected_path):
            os.remove(expected_path)
