"""Closer: trigger a snapshot shortly before each held bet's kickoff."""
from datetime import datetime, timedelta, timezone

from src.pipeline import closer

KO = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc)


def _state(*kickoffs, parlay_legs=()):
    bets = [{"kickoff": k.isoformat().replace("+00:00", "Z")} for k in kickoffs]
    parlays = [{"legs": [{"kickoff": k.isoformat().replace("+00:00", "Z")} for k in parlay_legs]}] \
        if parlay_legs else []
    return {"arms": {"A": {"active_bets": bets, "active_parlays": parlays}}}


def test_held_kickoffs_include_parlay_legs_and_dedupe():
    later = KO + timedelta(hours=2)
    got = closer.held_kickoffs(_state(KO, KO, parlay_legs=(KO, later)))
    assert got == {KO, later}


def test_nothing_is_due_before_the_lead_window():
    due, nxt = closer.plan({KO}, KO - timedelta(hours=1), set())
    assert due == [] and nxt == KO - closer.LEAD


def test_due_inside_the_lead_window():
    due, _ = closer.plan({KO}, KO - timedelta(minutes=10), set())
    assert due == [KO]


def test_a_late_start_still_closes_a_fixture_that_has_not_kicked_off():
    """A closer that starts after the window opened must still fire: the
    snapshot is later than ideal but the close is not lost."""
    due, _ = closer.plan({KO}, KO - timedelta(minutes=1), set())
    assert due == [KO]


def test_never_fires_once_the_match_has_started():
    """A price seen after kickoff is in-play, not a close."""
    due, nxt = closer.plan({KO}, KO, set())
    assert due == [] and nxt is None


def test_a_dispatched_kickoff_is_not_repeated():
    due, nxt = closer.plan({KO}, KO - timedelta(minutes=10), {KO})
    assert due == [] and nxt is None


def test_next_due_is_the_soonest_window():
    early, late = KO, KO + timedelta(hours=3)
    _, nxt = closer.plan({late, early}, KO - timedelta(hours=2), set())
    assert nxt == early - closer.LEAD


def test_undated_bets_are_ignored():
    state = {"arms": {"A": {"active_bets": [{"kickoff": None}, {"kickoff": "garbage"}],
                            "active_parlays": []}}}
    assert closer.held_kickoffs(state) == set()


def test_exits_when_nothing_is_held(monkeypatch):
    monkeypatch.setattr(closer, "_read_ledger", lambda: {"arms": {}})
    monkeypatch.setattr(closer, "_dispatch", lambda dry: (_ for _ in ()).throw(AssertionError))
    assert closer.main(["--budget-min", "5"]) == 0


def test_dispatches_then_exits_when_the_last_close_is_done(monkeypatch):
    now = datetime.now(timezone.utc)
    soon = now + timedelta(minutes=5)                  # already inside the lead window
    monkeypatch.setattr(closer, "_read_ledger", lambda: _state(soon))
    calls = []
    monkeypatch.setattr(closer, "_dispatch", lambda dry: calls.append(1) or True)
    assert closer.main(["--budget-min", "5"]) == 0
    assert calls == [1]
