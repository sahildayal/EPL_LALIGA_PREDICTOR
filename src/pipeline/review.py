"""
Phase 6a: the weekly plain-English review.

Runs after Tuesday's settle. Reads the season ledger and that run's settle log,
and asks Haiku for a short, readable summary: which arm is ahead, what CLV says,
what needs a human's attention. That is the whole job.

**This module never prices, stakes, or touches the ledger.** It is read-only
end to end — load the state, describe it, print the description. An LLM is a
poor tool for the one thing this project cannot get wrong (arithmetic on real
money-shaped numbers), and a fine tool for the one thing python is bad at
(explaining what a season of numbers means to a human in one paragraph). Haiku
was chosen deliberately over a larger model: this is short-context
summarization over structured data the harness already computed, not open-ended
reasoning, and that is exactly the class of task Haiku is priced for.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.market import ledger

LOG_DIR = Path("data/processed/matchweek_logs")
MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """\
You write a short weekly status note for a paper-money football betting \
experiment. Four strategies ("arms") each started the season with $10,000 \
of fake money; the experiment's whole point is comparing them honestly.

You will be given the current state of all four arms and the settle log from \
this week's run, as JSON. Write 4-8 sentences, plain prose, no headers, \
no bullet points, no emoji. Cover: which arm is currently ahead and by how \
much; what Closing Line Value (CLV) is showing, since CLV is this \
experiment's primary metric and matters more than raw profit at low sample \
sizes; anything in this week's settle log that looks like it needs a human's \
attention (a score dispute, an unrecognised team, bets still pending). If \
nothing needs attention, say so plainly in one sentence rather than omitting \
the topic.

Do not invent numbers. Every figure you state must come from the JSON you \
were given. If the data does not support a claim (e.g. too few settled bets \
to say anything about performance yet), say that plainly instead of reaching \
for something to say. Never suggest changing a strategy, a threshold, or a \
stake — this is a report, not a recommendation."""


@dataclass
class ReviewReport:
    ok: bool = False
    text: str = ""
    error: str = ""
    context: dict = field(default_factory=dict)

    def write(self) -> Path:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat().replace(":", "").replace("-", "")[:15]
        path = LOG_DIR / f"{stamp}_review.json"
        path.write_text(json.dumps(
            {"ok": self.ok, "text": self.text, "error": self.error}, indent=2))
        return path


def _latest_settle_log() -> dict:
    """The most recent settle run's log, or {} if none exists yet."""
    if not LOG_DIR.exists():
        return {}
    settles = sorted(LOG_DIR.glob("*_settle.json"))
    if not settles:
        return {}
    try:
        return json.loads(settles[-1].read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def build_context(state: dict = None) -> dict:
    """
    Everything the review needs, gathered once so the prompt and any manual
    inspection see the same snapshot.
    """
    state = state or ledger.load_state()
    settle_log = _latest_settle_log()
    return {
        "season": state.get("season"),
        "arms": ledger.season_summary(state),
        "latest_settle": {
            "started_utc": settle_log.get("started_utc"),
            "ok": settle_log.get("ok"),
            "errors": settle_log.get("errors", []),
            "settled": settle_log.get("details", {}).get("settled"),
            "still_pending": settle_log.get("details", {}).get("still_pending"),
            "voided": settle_log.get("details", {}).get("voided"),
        },
    }


def generate_review(context: dict, client=None) -> str:
    """
    Calls Haiku with the context and returns the plain-text summary.

    No thinking, no tools, no streaming: this is a short structured-JSON-in,
    prose-out summarization call over data the harness already computed, well
    under the token range where any of those would matter.
    """
    import anthropic
    client = client or anthropic.Anthropic()

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(context, indent=2, default=str)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Haiku declined to summarise this week's data (safety refusal).")
    return next(b.text for b in response.content if b.type == "text").strip()


def run_review() -> ReviewReport:
    """
    The job entry point. Never raises past this boundary — a broken review
    must not look like a broken settle, and must not block the ledger commit
    the same workflow run performs.
    """
    report = ReviewReport()
    try:
        context = build_context()
        report.context = context
        report.text = generate_review(context)
        report.ok = True
    except Exception as exc:
        report.error = f"{type(exc).__name__}: {exc}"
    report.write()
    return report
