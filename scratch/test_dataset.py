"""
Dataset tests, focused on the two defects this module exists to remove:
point-in-time leakage, and train/serve feature skew.
"""
import pandas as pd
import pytest

from src.data import dataset as D
from src.data.dataset import (
    DatasetUnavailable, FeatureBuilder, build_training_matrix, download_season,
    load_matches, season_codes,
)


# --- download_season: the 2026-08-20 incident -------------------------------
#
# football-data.co.uk's not-yet-published 2026/27 EPL file returned HTTP 300
# with an HTML "did you mean" page, not a 404. `raise_for_status()` only raises
# on 4xx/5xx and let the 300 through; the page was cached to disk and parsed as
# a one-column CSV, and the first real column lookup crashed the entire
# 27-season, both-league dataset build the morning before the EPL's opening
# weekend -- taking every OTHER season down with the one file that was never
# there.

class _FakeResponse:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content


def test_non_200_status_raises_without_caching(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "RAW_DIR", tmp_path)
    monkeypatch.setattr(D.requests, "get",
                        lambda url, timeout=40: _FakeResponse(300, b"<!DOCTYPE HTML><html>nope</html>"))
    with pytest.raises(DatasetUnavailable, match="HTTP 300"):
        download_season("epl", "2627")
    assert list(tmp_path.iterdir()) == []          # never written to the cache


def test_html_body_on_a_200_also_refuses_to_cache(tmp_path, monkeypatch):
    """Defense in depth: some other host quirk could return 200 with an error
    page body. Status alone is not sufficient evidence of a real CSV."""
    monkeypatch.setattr(D, "RAW_DIR", tmp_path)
    monkeypatch.setattr(D.requests, "get",
                        lambda url, timeout=40: _FakeResponse(200, b"<!doctype html><html>error</html>"))
    with pytest.raises(DatasetUnavailable, match="HTML"):
        download_season("epl", "2627")
    assert list(tmp_path.iterdir()) == []


def test_a_real_csv_is_cached_and_parsed(tmp_path, monkeypatch):
    csv = b"Date,HomeTeam,AwayTeam,FTHG,FTAG\n15/08/2026,Arsenal,Chelsea,2,0\n"
    monkeypatch.setattr(D, "RAW_DIR", tmp_path)
    monkeypatch.setattr(D.requests, "get", lambda url, timeout=40: _FakeResponse(200, csv))
    df = download_season("epl", "2627")
    assert len(df) == 1
    assert list(tmp_path.iterdir()) != []           # a genuine CSV IS cached


def test_one_broken_season_does_not_crash_the_whole_build(tmp_path, monkeypatch):
    """
    The second half of the incident: even with download_season fixed, one
    season/league combination shaped in a way nobody anticipated must cost
    only that combination, never the others being built in the same call.
    Mirrors the real shape of the incident: EPL's current season was broken
    while La Liga's current season, and every prior season of both leagues,
    were fine.
    """
    monkeypatch.setattr(D, "RAW_DIR", tmp_path)
    good = pd.DataFrame({"Date": ["15/08/2026"], "HomeTeam": ["Alaves"],
                         "AwayTeam": ["Getafe"], "FTHG": [1], "FTAG": [1]})
    current = season_codes(D.LAST_SEASON, D.LAST_SEASON)[0]

    def fake_download(league, season, refresh=False):
        if league == "epl" and season == current:
            raise KeyError("HomeTeam")               # simulates the unanticipated shape
        return good.copy()

    monkeypatch.setattr(D, "download_season", fake_download)
    df = load_matches(leagues=("epl", "laliga"), first=D.LAST_SEASON, last=D.LAST_SEASON)
    # EPL's current season contributed nothing, but La Liga's came through --
    # the whole call did not go down with the one broken combination.
    assert len(df) == 1 and set(df["league"]) == {"laliga"}


def match(date, home, away, hg, ag, season="2425", league="epl"):
    return {"date": pd.Timestamp(date), "league": league, "season": season,
            "home": home, "away": away, "home_goals": hg, "away_goals": ag,
            "home_shots": 10, "away_shots": 8, "home_sot": 4, "away_sot": 3,
            "home_corners": 5, "away_corners": 4}


FIXTURES = [
    match("2024-08-10", "arsenal", "chelsea", 2, 0),
    match("2024-08-17", "chelsea", "liverpool", 1, 1),
    match("2024-08-24", "arsenal", "liverpool", 3, 1),
    match("2024-08-31", "liverpool", "chelsea", 2, 2),
    match("2024-09-07", "chelsea", "arsenal", 0, 1),
]


def test_season_codes():
    assert season_codes(2000, 2000) == ["0001"]
    assert season_codes(2025, 2025) == ["2526"]
    assert len(season_codes(2000, 2025)) == 26


def test_first_ever_match_uses_priors_not_zeros():
    """A team with no history must get sensible priors, not 0.0 everywhere."""
    fb = FeatureBuilder()
    f = fb.features_for("arsenal", "chelsea", "2425", "2024-08-10")
    assert f["h_played"] == 0
    assert f["h_gf_pg"] == pytest.approx(1.35)      # prior, not zero
    assert f["h_ppg"] == pytest.approx(1.35)
    assert f["h_rest_days"] == 7.0


def test_features_reflect_only_prior_matches():
    fb = FeatureBuilder()
    # Before any match, Arsenal has no record.
    assert fb.features_for("arsenal", "chelsea", "2425", "2024-08-10")["h_played"] == 0
    fb.update("arsenal", "chelsea", "2425", pd.Timestamp("2024-08-10"), 2, 0)
    # After one win, exactly one match and 3 points.
    f = fb.features_for("arsenal", "liverpool", "2425", "2024-08-24")
    assert f["h_played"] == 1
    assert f["h_ppg"] == pytest.approx(3.0)
    assert f["h_gf_pg"] == pytest.approx(2.0)
    assert f["h_ga_pg"] == pytest.approx(0.0)


def test_no_lookahead_in_built_matrix():
    """
    The decisive leakage check: the features on match i must equal what a
    builder fed only matches 0..i-1 would produce.
    """
    df = build_training_matrix(pd.DataFrame(FIXTURES))
    for i in range(len(df)):
        replay = FeatureBuilder()
        for j in range(i):
            r = df.iloc[j]
            replay.update(r.home, r.away, r.season, r.date, r.home_goals, r.away_goals,
                          {k: r[k] for k in ("home_shots", "away_shots", "home_sot",
                                             "away_sot", "home_corners", "away_corners")})
        expected = replay.features_for(df.iloc[i].home, df.iloc[i].away,
                                       df.iloc[i].season, df.iloc[i].date)
        for k, v in expected.items():
            assert df.iloc[i][k] == pytest.approx(v), f"row {i} feature {k} leaked"


def test_train_and_serve_produce_identical_features():
    """
    The structural guarantee. Training features for the final fixture must be
    byte-identical to what the serve path produces for that same fixture when it
    is still upcoming. The old pipeline fabricated serve features
    (htgs = avg_goals * 10) and this is what silently broke.
    """
    history, upcoming = FIXTURES[:-1], FIXTURES[-1]

    # Training path: the fixture is the last row of a built matrix.
    train_row = build_training_matrix(pd.DataFrame(FIXTURES)).iloc[-1]

    # Serving path: replay history, then ask about the upcoming fixture.
    fb = FeatureBuilder()
    for m in history:
        fb.update(m["home"], m["away"], m["season"], m["date"], m["home_goals"], m["away_goals"],
                  {k: m[k] for k in ("home_shots", "away_shots", "home_sot",
                                     "away_sot", "home_corners", "away_corners")})
    serve = fb.features_for(upcoming["home"], upcoming["away"],
                            upcoming["season"], upcoming["date"])

    for k, v in serve.items():
        assert train_row[k] == pytest.approx(v), f"train/serve skew on {k}"


def test_season_table_resets_but_form_carries():
    fb = FeatureBuilder()
    for _ in range(5):
        fb.update("arsenal", "chelsea", "2324", pd.Timestamp("2024-01-01"), 3, 0)
    old = fb.features_for("arsenal", "chelsea", "2324", "2024-02-01")
    assert old["h_played"] == 5

    new = fb.features_for("arsenal", "chelsea", "2425", "2024-08-10")
    assert new["h_played"] == 0                     # league table resets
    assert new["h_form_gf"] == pytest.approx(3.0)   # form describes the team, carries over


def test_rest_days_computed_and_clamped():
    fb = FeatureBuilder()
    fb.update("arsenal", "chelsea", "2425", pd.Timestamp("2024-08-10"), 1, 0)
    assert fb.features_for("arsenal", "x", "2425", "2024-08-13")["h_rest_days"] == 3.0
    # A summer-long gap is clamped rather than producing an absurd value.
    assert fb.features_for("arsenal", "x", "2425", "2025-08-13")["h_rest_days"] == 30.0


def test_venue_splits_are_tracked_separately():
    fb = FeatureBuilder()
    fb.update("arsenal", "chelsea", "2425", pd.Timestamp("2024-08-10"), 4, 0)   # arsenal home
    fb.update("liverpool", "arsenal", "2425", pd.Timestamp("2024-08-17"), 0, 1)  # arsenal away
    f = fb.features_for("arsenal", "everton", "2425", "2024-08-24")
    assert f["h_venue_gf_pg"] == pytest.approx(4.0)     # home-only scoring rate
    assert f["h_gf_pg"] == pytest.approx(2.5)           # overall (4+1)/2


def test_diff_features_are_consistent():
    df = build_training_matrix(pd.DataFrame(FIXTURES))
    for _, r in df.iterrows():
        assert r["ppg_diff"] == pytest.approx(r["h_ppg"] - r["a_ppg"])
        assert r["gd_pg_diff"] == pytest.approx(r["h_gd_pg"] - r["a_gd_pg"])
        assert r["rest_diff"] == pytest.approx(r["h_rest_days"] - r["a_rest_days"])


def test_leagues_do_not_share_state():
    """A club's table in one league must not leak into another league's builder."""
    rows = [match("2024-08-10", "arsenal", "chelsea", 5, 0, league="epl"),
            match("2024-08-11", "barcelona", "sevilla", 0, 0, season="2425", league="laliga")]
    df = build_training_matrix(pd.DataFrame(rows))
    assert df.iloc[1]["h_played"] == 0
