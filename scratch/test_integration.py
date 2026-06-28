import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.scrapers.elo_db import get_national_elo
from src.data.scrapers.fbref import get_team_data, _get_espn_intl_form
from src.predictor import predict_match, PredictionResult

def test_integration():
    print("Running integration tests...")
    
    # 1. get_national_elo("Korea Republic") -> ELO score of South Korea (1832.0)
    elo = get_national_elo("Korea Republic")
    print(f"get_national_elo('Korea Republic') returned: {elo}")
    assert elo == 1832.0, f"Expected 1832.0, got {elo}"
    
    # 2. get_team_data("Korea Republic") -> South Korea averages
    team_data = get_team_data("Korea Republic")
    print(f"get_team_data('Korea Republic') returned: {team_data}")
    assert isinstance(team_data, dict), "Expected a dictionary"
    assert team_data.get("avg_goals") in (1.5, 1.0), f"Expected avg_goals 1.5 or 1.0, got {team_data.get('avg_goals')}"
    assert team_data.get("avg_conceded") == 1.0, f"Expected avg_conceded 1.0, got {team_data.get('avg_conceded')}"
    
    # 3. predict_match("Korea Republic", "United States") -> prediction result
    pred = predict_match("Korea Republic", "United States")
    print(f"predict_match('Korea Republic', 'United States') returned: {pred}")
    assert isinstance(pred, PredictionResult), "Expected a PredictionResult instance"
    assert pred.home == "Korea Republic", f"Expected home 'Korea Republic', got {pred.home}"
    assert pred.away == "United States", f"Expected away 'United States', got {pred.away}"
    assert "home_win" in pred.probabilities, "Expected 'home_win' in probabilities"
    assert "draw" in pred.probabilities, "Expected 'draw' in probabilities"
    assert "away_win" in pred.probabilities, "Expected 'away_win' in probabilities"
    
    # 4. _get_espn_intl_form("Korea Republic") -> form data success
    korea_form = _get_espn_intl_form("Korea Republic")
    print(f"_get_espn_intl_form('Korea Republic') returned: {korea_form}")
    assert isinstance(korea_form, dict), "Expected a dictionary"
    assert "form" in korea_form, "Expected 'form' in korea_form dict"
    assert any("ESPN" in ds for ds in korea_form.get("data_sources", [])), f"Expected ESPN data source, got {korea_form.get('data_sources')}"

    # 5. _get_espn_intl_form("United States") -> form data success
    usa_form = _get_espn_intl_form("United States")
    print(f"_get_espn_intl_form('United States') returned: {usa_form}")
    assert isinstance(usa_form, dict), "Expected a dictionary"
    assert "form" in usa_form, "Expected 'form' in usa_form dict"
    assert any("ESPN" in ds for ds in usa_form.get("data_sources", [])), f"Expected ESPN data source, got {usa_form.get('data_sources')}"
    
    test_paper_trading_normalization()
    print("\nALL INTEGRATION TESTS PASSED SUCCESSFULLY!")

def test_paper_trading_normalization():
    print("\nRunning paper trading integration tests...")
    import src.market.paper_trading as pt
    from src.market.paper_trading import place_bet, update_bet, resolve_pending_bets, get_personality_summary
    
    # Mock file path to not corrupt user state
    orig_path = pt.FILE_PATH
    test_path = os.path.join(pt.DATA_DIR, "test_paper_trading_temp.json")
    pt.FILE_PATH = test_path
    
    # Ensure starting clean
    if os.path.exists(test_path):
        os.remove(test_path)
        
    try:
        # 1. Place a bet for South Africa vs South Korea
        # Moneyline - South Korea Win
        # Stake: $50, Odds: 2.0
        res1 = update_bet("predict", "big_d", "South Africa", "South Korea", "Moneyline - South Korea Win", 50.0, 2.0)
        assert res1["action"] == "placed", f"Expected 'placed', got {res1.get('action')}"
        
        # Verify it exists in active bets
        summary = get_personality_summary("predict", "big_d")
        assert len(summary["active_bets"]) == 1, "Expected 1 active bet"
        active_bet = summary["active_bets"][0]
        assert active_bet["home"] == "south africa"
        assert active_bet["away"] == "south korea"
        assert active_bet["bet_type"] == "Moneyline - South Korea Win"
        assert active_bet["stake"] == 50.0
        assert active_bet["odds"] == 2.0
        
        # 2. Try placing the SAME bet but with swapped team order (SK vs SA)
        # It should recognize the existing position and return action "none"
        res2 = update_bet("predict", "big_d", "South Korea", "South Africa", "Moneyline - South Korea Win", 50.0, 2.0)
        assert res2["action"] == "none", f"Expected 'none', got {res2.get('action')}"
        
        # 3. Resolve the bet with a completed match result:
        # Completed match has home = "Korea Republic", away = "South Africa" (swapped order relative to placed bet)
        # Score: Korea Republic 2, South Africa 1.
        # Since South Korea (Korea Republic) won 2-1, "Moneyline - South Korea Win" should win!
        resolved = resolve_pending_bets("Korea Republic", "South Africa", 2, 1)
        assert len(resolved) == 1, f"Expected 1 resolved bet, got {len(resolved)}"
        portfolio, personality, bet_res = resolved[0]
        assert portfolio == "predict"
        assert personality == "big_d"
        assert bet_res["result"] == "WIN"
        assert bet_res["pnl"] == 50.0
        
        # Bankroll should be updated: 1000 - 50 (placed) + 100 (won payout) = 1050
        summary_after = get_personality_summary("predict", "big_d")
        assert summary_after["bankroll"] == 1050.0, f"Expected bankroll 1050.0, got {summary_after['bankroll']}"
        assert len(summary_after["active_bets"]) == 0, "Expected 0 active bets after resolution"
        assert len(summary_after["recent_bets"]) == 1, "Expected 1 resolved bet in history"
        
        print("Paper trading integration tests PASSED!")
    finally:
        # Cleanup
        if os.path.exists(test_path):
            os.remove(test_path)
        pt.FILE_PATH = orig_path

if __name__ == "__main__":
    test_integration()
