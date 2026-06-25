import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.team_mapping import normalize_team_name, is_team_match

def run_tests():
    # Test normalization
    assert normalize_team_name("Korea Republic") == "south korea"
    assert normalize_team_name("south korea") == "south korea"
    assert normalize_team_name("United States") == "usa"
    assert normalize_team_name("usa") == "usa"
    assert normalize_team_name("Czechia") == "czech republic"
    
    # Test matching
    assert is_team_match("South Korea", "Korea Republic Winner?") == True
    assert is_team_match("South Korea", "KXWCGAME-26JUN24RSAKOR-KOR") == False  # Suffixes should not match blindly, but event titles will
    assert is_team_match("South Africa", "South Africa vs Korea Republic") == True
    assert is_team_match("South Korea", "South Africa vs Korea Republic") == True
    
    print("ALL TEAM MAPPING TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
