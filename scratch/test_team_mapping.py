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
    assert normalize_team_name("Twin") == "twin"  # Greedy substring test
    
    # Test matching
    assert is_team_match("South Korea", "Korea Republic Winner?") == True
    assert is_team_match("South Korea", "KXWCGAME-26JUN24RSAKOR-KOR") == False  # Suffixes should not match blindly, but event titles will
    assert is_team_match("South Africa", "South Africa vs Korea Republic") == True
    assert is_team_match("South Korea", "South Africa vs Korea Republic") == True
    
    # Crucial Bug / Country collisions test cases
    assert is_team_match("South Korea", "North Korea") == False
    assert is_team_match("Ireland", "Northern Ireland") == False
    assert is_team_match("North Korea", "South Korea") == False
    assert is_team_match("Northern Ireland", "Ireland") == False
    assert is_team_match("Ireland", "Republic of Ireland") == True
    assert is_team_match("Ireland", "Ireland vs Northern Ireland") == True
    assert is_team_match("Northern Ireland", "Ireland vs Northern Ireland") == True
    
    # Suffix normalization boundaries
    assert normalize_team_name("win") == ""
    assert normalize_team_name("winner") == ""
    assert normalize_team_name("to win") == ""
    assert normalize_team_name("team to win") == "team"
    assert normalize_team_name("team to score") == "team"
    assert normalize_team_name("team goal") == "team"
    
    # New Guinea alias
    assert normalize_team_name("new guinea") == "papua new guinea"
    
    # Congo collision tests
    assert normalize_team_name("congo") == "congo"
    assert is_team_match("congo dr", "congo") == False
    assert is_team_match("congo", "congo dr") == False
    assert is_team_match("congo dr", "Democratic Republic of the Congo") == True
    
    print("ALL TEAM MAPPING TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
