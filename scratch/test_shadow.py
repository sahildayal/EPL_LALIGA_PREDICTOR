"""The shadow ledger records every priced market and joins it to its close and result."""
from datetime import datetime, timezone

import pytest

from src.market import shadow
from src.market.grading import MatchResult


@pytest.fixture(autouse=True)
def _tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow, "SHADOW_DIR", tmp_path / "shadow")


NOW = datetime(2026, 11, 27, 10, tzinfo=timezone.utc)
MKTS = [
    {"home": "arsenal", "away": "chelsea", "market": "1x2", "selection": "home",
     "ask": 0.52, "bid": 0.50, "league": "epl", "kickoff": "2026-11-28T15:00:00Z"},
    {"home": "arsenal", "away": "chelsea", "market": "1x2", "selection": "not_home",
     "ask": 0.50, "bid": 0.48, "league": "epl", "kickoff": "2026-11-28T15:00:00Z"},
    {"home": "arsenal", "away": "chelsea", "market": "totals", "selection": "over",
     "line": 4.5, "ask": 0.10, "league": "epl", "kickoff": "2026-11-28T15:00:00Z"},
]
FAIR = {("arsenal", "chelsea"): {"1x2": {"home": 0.50, "draw": 0.27, "away": 0.23},
                                 "totals": {"over": 0.55, "under": 0.45, "_line": 2.5}}}
MODEL = {("arsenal", "chelsea"): {"1x2": {"home": 0.60, "draw": 0.25, "away": 0.15}}}


def test_observations_record_both_prices_and_skip_unpriceable_lines():
    n = shadow.record_observations(MKTS, FAIR, MODEL, "stake", now=NOW)
    assert n == 2                       # the Over 4.5 has no fair value at that line
    rows = shadow._read("observations")
    home = next(r for r in rows if r["key"][3] == "home")
    assert home["fair"] == 0.5 and home["model"] == 0.6 and home["bid"] == 0.50


def test_join_attaches_close_and_grades_the_result():
    shadow.record_observations(MKTS, FAIR, MODEL, "stake", now=NOW)
    shadow.record_observations(MKTS, FAIR, MODEL, "stake",
                               now=datetime(2026, 11, 28, 6, tzinfo=timezone.utc))
    late = [dict(m, ask=m["ask"] - 0.02, bid=(m.get("bid") or 0.02) - 0.02) for m in MKTS]
    shadow.record_closes(late, now=datetime(2026, 11, 28, 14, 30, tzinfo=timezone.utc))
    # a stamp after kickoff must never be recorded as the close
    shadow.record_closes(MKTS, now=datetime(2026, 11, 28, 15, 5, tzinfo=timezone.utc))
    shadow.record_results([MatchResult("arsenal", "chelsea", 0, 0)], now=NOW)

    rows = {r["key"][3]: r for r in shadow.joined()}
    assert len(rows) == 2               # first observation only
    assert rows["home"]["ts"].startswith("2026-11-27")
    assert rows["home"]["close_ask"] == pytest.approx(0.50)
    assert rows["home"]["won"] is False and rows["not_home"]["won"] is True
    assert rows["home"]["close_mid"] == pytest.approx(0.49)


def test_close_window_only_covers_the_hours_before_kickoff():
    assert shadow.record_closes(MKTS, now=NOW) == 0    # 29h out: too early
