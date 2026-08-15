"""
Phase 6a: the weekly plain-English review. Fully mocked -- no real Anthropic
calls, no real ledger, no network.

The one property every test here protects: this module is READ-ONLY. It must
never be able to place a bet, size a stake, or write to the ledger, no matter
what the model returns.
"""
import json

import pytest

from src.market import ledger
from src.pipeline import review as R


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ledger, "LEDGER_PATH", str(tmp_path / "season_ledger.json"))
    monkeypatch.setattr(R, "LOG_DIR", tmp_path / "logs")
    yield


class _FakeTextBlock:
    type = "text"
    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_FakeTextBlock(text)]
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, text="A vs B, C ahead.", stop_reason="end_turn"):
        self._text = text
        self._stop_reason = stop_reason
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._text, self._stop_reason)


class _FakeClient:
    def __init__(self, text="A vs B, C ahead.", stop_reason="end_turn"):
        self.messages = _FakeMessages(text, stop_reason)


# --- Context building ---------------------------------------------------------

def test_context_includes_every_arm():
    ctx = R.build_context()
    assert len(ctx["arms"]) == 4
    assert ctx["season"] == "2026-27"


def test_context_with_no_settle_log_yet_is_empty_not_missing():
    ctx = R.build_context()
    assert ctx["latest_settle"]["started_utc"] is None
    assert ctx["latest_settle"]["errors"] == []


def test_context_picks_the_most_recent_settle_log(tmp_path):
    R.LOG_DIR.mkdir(parents=True, exist_ok=True)
    (R.LOG_DIR / "20260804T090000_settle.json").write_text(
        json.dumps({"started_utc": "old", "ok": True, "errors": [], "details": {}}))
    (R.LOG_DIR / "20260811T090000_settle.json").write_text(
        json.dumps({"started_utc": "new", "ok": True, "errors": [],
                   "details": {"settled": 3, "still_pending": 0, "voided": 0}}))
    ctx = R.build_context()
    assert ctx["latest_settle"]["started_utc"] == "new"
    assert ctx["latest_settle"]["settled"] == 3


def test_context_ignores_non_settle_logs(tmp_path):
    R.LOG_DIR.mkdir(parents=True, exist_ok=True)
    (R.LOG_DIR / "20260808T110000_snapshot.json").write_text(
        json.dumps({"started_utc": "snap", "ok": True}))
    ctx = R.build_context()
    assert ctx["latest_settle"]["started_utc"] is None


def test_corrupt_settle_log_does_not_crash_context(tmp_path):
    R.LOG_DIR.mkdir(parents=True, exist_ok=True)
    (R.LOG_DIR / "20260811T090000_settle.json").write_text("{not json")
    ctx = R.build_context()
    assert ctx["latest_settle"]["started_utc"] is None


# --- generate_review -----------------------------------------------------------

def test_generate_review_returns_the_model_text():
    fake = _FakeClient(text="Arm C leads this week.")
    out = R.generate_review({"season": "2026-27"}, client=fake)
    assert out == "Arm C leads this week."


def test_generate_review_sends_the_context_as_the_user_message():
    fake = _FakeClient()
    ctx = {"season": "2026-27", "arms": [{"arm": "A"}]}
    R.generate_review(ctx, client=fake)
    sent = fake.messages.calls[0]
    assert sent["model"] == "claude-haiku-4-5"
    assert json.loads(sent["messages"][0]["content"]) == ctx


def test_generate_review_uses_no_thinking_and_no_tools():
    """
    A short structured-JSON-in, prose-out summary over data the harness already
    computed does not need thinking, tools, or streaming -- confirming the call
    stays a plain, cheap Messages request rather than growing scope silently.
    """
    fake = _FakeClient()
    R.generate_review({}, client=fake)
    sent = fake.messages.calls[0]
    assert "thinking" not in sent
    assert "tools" not in sent


def test_refusal_raises_rather_than_returning_empty_text():
    fake = _FakeClient(text="", stop_reason="refusal")
    with pytest.raises(RuntimeError, match="declined"):
        R.generate_review({}, client=fake)


# --- run_review: the advisory contract ------------------------------------

def test_run_review_never_raises_on_a_broken_client(monkeypatch):
    def boom(context, client=None):
        raise RuntimeError("API is down")
    monkeypatch.setattr(R, "generate_review", boom)
    report = R.run_review()
    assert report.ok is False
    assert "API is down" in report.error


def test_run_review_succeeds_and_writes_a_log(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "generate_review", lambda ctx, client=None: "All quiet this week.")
    report = R.run_review()
    assert report.ok and report.text == "All quiet this week."
    files = list(R.LOG_DIR.glob("*_review.json"))
    assert len(files) == 1
    logged = json.loads(files[0].read_text())
    assert logged["ok"] is True and logged["text"] == "All quiet this week."


def test_run_review_touches_nothing_in_the_ledger(monkeypatch):
    """The one property this module must never violate: it is read-only."""
    monkeypatch.setattr(R, "generate_review", lambda ctx, client=None: "Summary.")
    before = ledger.load_state()
    R.run_review()
    after = ledger.load_state()
    assert before == after
    for book in after["arms"].values():
        assert book["bankroll"] == 10_000.0
        assert book["active_bets"] == [] and book["history"] == []


# --- CLI wiring ------------------------------------------------------------

def test_cli_review_always_exits_zero_even_on_failure(monkeypatch, capsys):
    from src.pipeline import run as cli

    class Failing:
        ok, text, error = False, "", "boom: network"
    monkeypatch.setattr("src.pipeline.review.run_review", lambda: Failing())
    code = cli.main(["review"])
    assert code == cli.EXIT_OK          # advisory: never fails the workflow
    assert "REVIEW FAILED" in capsys.readouterr().out


def test_cli_review_prints_the_text_on_success(monkeypatch, capsys):
    from src.pipeline import run as cli

    class Ok:
        ok, text = True, "Arm A is up $120."
    monkeypatch.setattr("src.pipeline.review.run_review", lambda: Ok())
    cli.main(["review"])
    assert "Arm A is up $120." in capsys.readouterr().out
