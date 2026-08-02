"""
Results collection and settlement plumbing.

Everything here is mocked. A test that needs the live ESPN feed cannot gate a
deploy, and settlement is precisely the code that must not be deployed untested.
"""
import json
from datetime import date

import pytest

from src.pipeline import results as R
from src.pipeline import run as cli


def event(home="Arsenal", away="Chelsea", hs="2", as_="1",
          status="STATUS_FINAL", completed=True, date_str="2026-08-22T14:00Z"):
    return {
        "id": "1", "date": date_str,
        "competitions": [{
            "status": {"type": {"name": status, "completed": completed}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": home}, "score": hs},
                {"homeAway": "away", "team": {"displayName": away}, "score": as_},
            ],
        }],
    }


# --- Event parsing -----------------------------------------------------------

def test_completed_match_becomes_a_result():
    rec = R._parse_event(event())
    assert rec["kind"] == "result"
    assert (rec["home_goals"], rec["away_goals"]) == (2, 1)


def test_postponed_match_becomes_a_void_not_a_result():
    rec = R._parse_event(event(status="STATUS_POSTPONED", completed=False))
    assert rec["kind"] == "void" and rec["reason"] == "postponed"


@pytest.mark.parametrize("status,reason", [
    ("STATUS_CANCELED", "cancelled"),
    ("STATUS_ABANDONED", "abandoned"),
    ("STATUS_SUSPENDED", "suspended"),
])
def test_every_non_playing_status_voids(status, reason):
    assert R._parse_event(event(status=status, completed=False))["reason"] == reason


def test_in_progress_match_is_pending():
    rec = R._parse_event(event(status="STATUS_IN_PROGRESS", completed=False))
    assert rec["kind"] == "pending"


def test_completed_without_a_score_is_pending_not_zero_zero():
    """Inventing 0-0 for a match ESPN could not score is the fabrication class."""
    rec = R._parse_event(event(hs=None, as_=None))
    assert rec["kind"] == "pending"


def test_unrecognised_team_is_surfaced_not_dropped():
    """
    A silently skipped fixture leaves its bets pending forever with no
    explanation, which looks identical to a match that has not been played.
    """
    rec = R._parse_event(event(home="Some FC That Does Not Exist"))
    assert rec["kind"] == "unknown_team"


def test_malformed_event_is_ignored():
    assert R._parse_event({"competitions": []}) is None
    assert R._parse_event({"competitions": [{"competitors": []}]}) is None


# --- Sweep -------------------------------------------------------------------

def _fake_get(payload_by_call):
    calls = {"n": 0}

    class Resp:
        def __init__(self, data):
            self._d = data
        def json(self):
            return self._d

    def _get(url, params=None, timeout=20):
        calls["n"] += 1
        return Resp(payload_by_call(url, params, calls["n"]))
    return _get, calls


def test_sweep_collects_results_and_voids(monkeypatch):
    def payload(url, params, n):
        if n == 1:
            return {"events": [event()]}
        if n == 2:
            return {"events": [event(home="Liverpool", away="Everton",
                                     status="STATUS_POSTPONED", completed=False)]}
        return {"events": []}
    monkeypatch.setattr(R, "_get", _fake_get(payload)[0])
    out = R.fetch_espn(days_back=1, today=date(2026, 8, 24))
    assert ("arsenal", "chelsea") in out["results"]
    assert ("liverpool", "everton") in out["voids"]


def test_a_replayed_fixture_is_not_voided(monkeypatch):
    """Postponed on Saturday, played on Wednesday: that is a result, not a void."""
    def payload(url, params, n):
        if n == 1:
            return {"events": [event(status="STATUS_POSTPONED", completed=False)]}
        if n == 2:
            return {"events": [event()]}
        return {"events": []}
    monkeypatch.setattr(R, "_get", _fake_get(payload)[0])
    out = R.fetch_espn(days_back=1, today=date(2026, 8, 24))
    assert ("arsenal", "chelsea") in out["results"]
    assert out["voids"] == {}


def test_total_feed_outage_raises_rather_than_settling_nothing(monkeypatch):
    """
    Silently settling zero matches on a dead feed looks exactly like a week with
    no fixtures, and the bets would sit pending with no alert.
    """
    def boom(url, params=None, timeout=20):
        raise R.ResultsUnavailable("network down")
    monkeypatch.setattr(R, "_get", boom)
    with pytest.raises(R.ResultsUnavailable):
        R.fetch_espn(days_back=1, today=date(2026, 8, 24))


def test_partial_outage_still_returns_what_it_has(monkeypatch):
    def flaky(url, params=None, timeout=20):
        if params["dates"].endswith("24"):
            raise R.ResultsUnavailable("timeout")
        class Resp:
            def json(self): return {"events": [event()]}
        return Resp()
    monkeypatch.setattr(R, "_get", flaky)
    out = R.fetch_espn(days_back=1, today=date(2026, 8, 24))
    assert out["requests_failed"] > 0 and out["requests_ok"] > 0
    assert ("arsenal", "chelsea") in out["results"]


# --- Reconciliation ----------------------------------------------------------

def test_season_code_spans_the_calendar_year():
    assert R._season_code(date(2026, 8, 15)) == "2627"
    assert R._season_code(date(2027, 3, 1)) == "2627"     # still the 26/27 season
    assert R._season_code(date(2027, 7, 1)) == "2728"


def test_matching_scores_are_confirmed():
    espn = {("arsenal", "chelsea"): {"home_goals": 2, "away_goals": 1}}
    arch = {("arsenal", "chelsea"): {"home_goals": 2, "away_goals": 1}}
    assert R.reconcile(espn, arch)["confirmed"] == 1


def test_a_corrected_score_is_reported_not_silently_applied():
    """
    Auto-correcting a settled bet from a scraper disagreement is how a public
    ledger stops being trustworthy. It goes to a human.
    """
    espn = {("arsenal", "chelsea"): {"home_goals": 2, "away_goals": 1}}
    arch = {("arsenal", "chelsea"): {"home_goals": 2, "away_goals": 2}}
    out = R.reconcile(espn, arch)
    assert out["confirmed"] == 0 and len(out["mismatches"]) == 1
    assert out["mismatches"][0]["espn"] == [2, 1]
    assert out["mismatches"][0]["football_data"] == [2, 2]


def test_fixtures_not_yet_archived_are_not_mismatches():
    espn = {("arsenal", "chelsea"): {"home_goals": 2, "away_goals": 1}}
    out = R.reconcile(espn, {})
    assert out["mismatches"] == [] and len(out["awaiting_archive"]) == 1


# --- Settle job --------------------------------------------------------------

def test_settle_reports_a_mismatch_as_a_warning(monkeypatch, tmp_path):
    from src.market import ledger
    from src.market.grading import MatchResult
    from src.pipeline import matchweek
    monkeypatch.setattr(ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ledger, "LEDGER_PATH", str(tmp_path / "l.json"))
    monkeypatch.setattr(matchweek, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(R, "collect", lambda **kw: {
        "results": [MatchResult(home="arsenal", away="chelsea", home_goals=2, away_goals=1)],
        "voids": [],
        "reconciliation": {"confirmed": 0, "mismatches": [{"fixture": ["arsenal", "chelsea"],
                                                           "espn": [2, 1],
                                                           "football_data": [2, 2]}],
                           "awaiting_archive": []},
        "pending_fixtures": [], "unknown_teams": [],
        "requests_ok": 2, "requests_failed": 0,
    })
    report = matchweek.run_settle()
    # The settle itself worked; the disagreement is advisory but must be loud.
    assert report.ok
    assert any("SCORE MISMATCH" in e for e in report.errors)


def test_settle_voids_a_postponed_fixture(monkeypatch, tmp_path):
    from src.market import ledger
    from src.market.grading import Bet
    from src.pipeline import matchweek
    monkeypatch.setattr(ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ledger, "LEDGER_PATH", str(tmp_path / "l.json"))
    monkeypatch.setattr(matchweek, "LOG_DIR", tmp_path / "logs")
    ledger.place_bet("A_divergence_kelly",
                     Bet(market="1x2", selection="home", home="arsenal",
                         away="chelsea", stake=100.0, price=0.5))
    report = matchweek.run_settle(results=[], voids=[("arsenal", "chelsea", "postponed")])
    assert report.ok and report.details["voided"] == 1
    assert ledger.load_state()["arms"]["A_divergence_kelly"]["bankroll"] == 10_000.0


# --- CLI ---------------------------------------------------------------------

class FakeReport:
    def __init__(self, ok, errors=None):
        self.job, self.started_utc = "settle", "2026-08-25T09:00:00Z"
        self.ok, self.errors = ok, errors or []
        self.details = {"settled": 3}


def test_cli_exit_codes_distinguish_warn_from_fail(monkeypatch, capsys):
    """
    A settle that graded a bet on a disputed score must not look like a clean
    week to the workflow, and a failed run must not look like a warning.
    """
    from src.pipeline import matchweek
    monkeypatch.setattr(matchweek, "run_settle", lambda: FakeReport(True))
    assert cli.main(["settle"]) == cli.EXIT_OK

    monkeypatch.setattr(matchweek, "run_settle", lambda: FakeReport(True, ["mismatch"]))
    assert cli.main(["settle"]) == cli.EXIT_WARN

    monkeypatch.setattr(matchweek, "run_settle", lambda: FakeReport(False, ["boom"]))
    assert cli.main(["settle"]) == cli.EXIT_FAILED


def test_cli_emits_parseable_json(monkeypatch, capsys):
    from src.pipeline import matchweek
    monkeypatch.setattr(matchweek, "run_settle", lambda: FakeReport(True))
    cli.main(["settle"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"] == "settle" and payload["ok"] is True


def test_cli_dry_run_reaches_the_stake_job(monkeypatch):
    seen = {}
    from src.pipeline import matchweek
    def fake(dry_run=False):
        seen["dry"] = dry_run
        return FakeReport(True)
    monkeypatch.setattr(matchweek, "run_stake", fake)
    cli.main(["stake", "--dry-run"])
    assert seen["dry"] is True
