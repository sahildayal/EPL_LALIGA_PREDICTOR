"""
The shadow ledger: every market the stake job prices, whether or not any arm bets.

Arms A and B have placed two bets all season. Across 1,356 priced markets from
25 Sep to 22 Nov only 4 cleared +0.5% net edge and none cleared 1.5%, so
lowering a threshold cannot buy volume, and the season's question ("does Kalshi
diverge from the sharp line by more than its fee?") cannot be answered from the
arms' bets alone. This records the evidence instead: every observed market with
its ask, bid, sharp fair value and model price, its closing price, and the
final score, so the edge can be measured at every threshold at once and the
favourite-longshot bias tested by price bucket.

Nothing here places, sizes or influences a bet.

Storage is three APPEND-ONLY JSONL files per month under data/processed/shadow/:

    observations_YYYY-MM.jsonl   one row per market per stake run
    closes_YYYY-MM.jsonl         pre-kickoff asks/bids seen by snapshots
    results_YYYY-MM.jsonl        final scores seen by settle

They are joined only when a report is built (`scripts/shadow_report.py`).
Append-only keeps the committed diffs small (the ledger is committed after
every run) and means no run can rewrite an earlier row.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.market.edge import build_opportunities

SHADOW_DIR = Path("data/processed/shadow")

#: Snapshots record a close for a market only inside this window before its
#: kickoff. The last one recorded before kickoff is the close.
CLOSE_WINDOW_H = 4


def _append(kind: str, rows: list, now: datetime) -> int:
    if not rows:
        return 0
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    path = SHADOW_DIR / f"{kind}_{now:%Y-%m}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":"), default=str) + "\n")
    return len(rows)


def _key(m: dict) -> list:
    line = m.get("line")
    return [m.get("home"), m.get("away"), m.get("market"), m.get("selection"),
            None if line is None else round(float(line), 1)]


def _kickoff(raw):
    try:
        ko = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return ko if ko.tzinfo else ko.replace(tzinfo=timezone.utc)


def record_observations(markets: list, fair: dict, model: dict, job: str,
                        now: datetime = None) -> int:
    """One row per bettable Kalshi market, priced both ways. Returns rows written."""
    now = now or datetime.now(timezone.utc)
    sharp = {tuple(_key(vars(o))): o for o in build_opportunities(markets, fair)}
    modelled = {tuple(_key(vars(o))): o
                for o in build_opportunities(markets, {}, model, allow_model_priced=True)}
    rows = []
    for m in markets:
        k = _key(m)
        s, md = sharp.get(tuple(_canon(k))), modelled.get(tuple(_canon(k)))
        if s is None and md is None:
            continue
        rows.append({
            "ts": now.isoformat(), "job": job, "league": m.get("league"),
            "key": _canon(k), "kickoff": m.get("kickoff"), "ticker": m.get("ticker"),
            "ask": m.get("ask"), "bid": m.get("bid"),
            "fair": None if s is None else round(s.fair_prob, 5),
            "fair_source": None if s is None else s.fair_source,
            "net_edge": None if s is None else round(s.net_edge, 5),
            "model": None if md is None else round(md.fair_prob, 5),
            "model_net_edge": None if md is None else round(md.net_edge, 5),
        })
    return _append("observations", rows, now)


def _canon(k: list) -> list:
    """build_opportunities canonicalises club names; match its keys."""
    from src.data.canonical_teams import canonical
    return [canonical(k[0], strict=False), canonical(k[1], strict=False)] + k[2:]


def record_closes(markets: list, now: datetime = None) -> int:
    """Asks and bids of markets kicking off within CLOSE_WINDOW_H, never after kickoff."""
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=CLOSE_WINDOW_H)
    rows = []
    for m in markets:
        ko = _kickoff(m.get("kickoff"))
        if ko is None or not (now < ko <= horizon):
            continue
        rows.append({"ts": now.isoformat(), "key": _canon(_key(m)),
                     "ask": m.get("ask"), "bid": m.get("bid")})
    return _append("closes", rows, now)


def record_results(results: list, now: datetime = None) -> int:
    """Final scores from settle. Duplicates across runs are harmless; the join dedups."""
    now = now or datetime.now(timezone.utc)
    rows = [{"ts": now.isoformat(), "home": r.home, "away": r.away,
             "home_goals": r.home_goals, "away_goals": r.away_goals}
            for r in results or []]
    return _append("results", rows, now)


def _read(kind: str) -> list:
    out = []
    for path in sorted(SHADOW_DIR.glob(f"{kind}_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def joined(first_only: bool = True) -> list:
    """
    Observations with their close and outcome attached.

    `first_only` keeps each market's FIRST observation (the earliest moment any
    arm could have bet it), so a market priced on Friday, Sunday and Tuesday
    counts once. Each row gains `close_ask`, `close_bid`, `won` (None until a
    result is recorded) and `close_mid`.
    """
    from src.market.grading import Bet, MatchResult, UngradeableBet, grade

    obs = _read("observations")
    if first_only:
        seen, kept = set(), []
        for o in sorted(obs, key=lambda o: o["ts"]):
            k = tuple(o["key"])
            if k not in seen:
                seen.add(k)
                kept.append(o)
        obs = kept

    closes = {}
    for c in sorted(_read("closes"), key=lambda c: c["ts"]):
        closes[tuple(c["key"])] = c           # latest pre-kickoff stamp wins
    results = {(r["home"], r["away"]): r for r in _read("results")}

    out = []
    for o in obs:
        row = dict(o)
        c = closes.get(tuple(o["key"]))
        row["close_ask"] = c.get("ask") if c else None
        row["close_bid"] = c.get("bid") if c else None
        row["close_mid"] = (round((c["ask"] + c["bid"]) / 2, 5)
                            if c and c.get("ask") and c.get("bid") else None)
        home, away, market, selection, line = o["key"]
        r = results.get((home, away))
        row["won"] = None
        if r:
            try:
                row["won"] = grade(
                    Bet(market=market, selection=selection, home=home, away=away,
                        stake=1.0, price=o["ask"], line=line),
                    MatchResult(home, away, r["home_goals"], r["away_goals"]))
            except UngradeableBet:
                pass
        out.append(row)
    return out
