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
    assert team_data.get("avg_goals") == 1.5, f"Expected avg_goals 1.5, got {team_data.get('avg_goals')}"
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
    
    print("\nALL INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_integration()
