"""Team-name registry tests. A wrong resolution here prices the wrong team."""
import pytest

from src.data.canonical_teams import (
    canonical, league_of, is_known, unknown_names, UnknownTeam, TEAMS, EPL, LALIGA,
)


@pytest.mark.parametrize("variants,expected", [
    # The four sources spell these differently; all must collapse to one key.
    (["Man United", "Manchester United", "Man Utd", "manchester utd"], "manchester united"),
    (["Man City", "Manchester City"], "manchester city"),
    (["Nott'm Forest", "Forest", "Nottingham Forest"], "nottingham forest"),
    (["Ath Bilbao", "Bilbao", "Athletic Club", "Athletic Bilbao"], "athletic bilbao"),
    (["Ath Madrid", "Atletico", "Atlético Madrid", "Atletico Madrid"], "atletico madrid"),
    (["Vallecano", "Rayo Vallecano", "Rayo"], "rayo vallecano"),
    (["Sociedad", "Real Sociedad"], "real sociedad"),
    (["Celta", "Celta Vigo", "RC Celta"], "celta vigo"),
    (["Betis", "Real Betis"], "real betis"),
    (["Espanol", "Espanyol", "RCD Espanyol"], "espanyol"),
    (["Wolves", "Wolverhampton Wanderers"], "wolverhampton"),
    (["Spurs", "Tottenham", "Tottenham Hotspur"], "tottenham"),
    (["Brighton", "Brighton & Hove Albion"], "brighton"),
    (["Bournemouth", "AFC Bournemouth"], "bournemouth"),
    # Promoted 2026/27 clubs, where ClubElo uses very short forms
    (["Santander", "Real Racing Club de Santander"], "racing santander"),
    (["Depor", "Deportivo La Coruña", "Deportivo"], "deportivo la coruna"),
    # football-data.co.uk's 2026/27 file spells the club with the Galician
    # "A Coruna" rather than the Spanish "La Coruna" used every prior season.
    # Missing this alias split one club's record into two canonical keys and
    # handed the model a "new" team with no history -- found 2026-08-20.
    (["Dep. A Coruna", "Dep A Coruna", "Deportivo A Coruna"], "deportivo la coruna"),
    (["Malaga", "Málaga", "Malaga CF"], "malaga"),
    (["Oviedo", "Real Oviedo"], "real oviedo"),
])
def test_all_source_spellings_collapse_to_one_key(variants, expected):
    for v in variants:
        assert canonical(v) == expected, f"{v!r} did not resolve to {expected!r}"


def test_accents_and_punctuation_are_stripped():
    assert canonical("Alavés") == canonical("Alaves") == "alaves"
    assert canonical("Nott'm Forest") == canonical("Nottm Forest")


def test_case_collisions_are_impossible():
    """The old pipeline fitted 'England' and 'england' as two different teams."""
    for name in ["ARSENAL", "Arsenal", "arsenal", "  Arsenal  "]:
        assert canonical(name) == "arsenal"


def test_unknown_team_raises_rather_than_inventing_one():
    with pytest.raises(UnknownTeam):
        canonical("Wednesfield Wanderers FC")
    with pytest.raises(UnknownTeam):
        canonical("")


def test_lenient_mode_returns_slug_without_raising():
    assert canonical("Wednesfield Wanderers FC", strict=False) == "wednesfield wanderers fc"


def test_league_lookup():
    assert league_of("Man United") == EPL
    assert league_of("Ath Bilbao") == LALIGA


def test_every_canonical_name_resolves_to_itself():
    for name in TEAMS:
        assert canonical(name) == name


def test_no_alias_maps_to_a_nonexistent_canonical():
    from src.data.canonical_teams import ALIASES
    dangling = {a: c for a, c in ALIASES.items() if c not in TEAMS}
    assert not dangling, f"aliases point at unknown canonical names: {dangling}"


def test_is_known_and_unknown_names():
    assert is_known("Man Utd") and not is_known("Nowhere United")
    assert unknown_names(["Arsenal", "Nowhere United"]) == ["Nowhere United"]
