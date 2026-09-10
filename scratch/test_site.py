"""Dashboard generator: renders from committed state, and only committed state."""
import json

import pytest

from src.report import site


def _ledger(**arm_over):
    base = {
        "schema_version": 3,
        "season": "2026-27",
        "created_utc": "2026-08-02T00:00:00+00:00",
        "arms": {},
    }
    for key, _, label, _ in site.ARMS:
        base["arms"][key] = {
            "label": label, "bankroll": 10000.0, "starting_bankroll": 10000.0,
            "active_bets": [], "history": [], "active_parlays": [], "parlay_history": [],
        }
    for key, over in arm_over.items():
        base["arms"][key].update(over)
    return base


def _bet(**kw):
    b = {
        "market": "1x2", "selection": "home", "home": "arsenal", "away": "chelsea",
        "stake": 100.0, "price": 0.40, "line": None, "prop": None,
        "label": "Arsenal vs Chelsea — Moneyline: Arsenal Win", "league": "epl",
        "kickoff": "2026-08-22T14:00:00Z", "model_prob": 0.5, "fair_prob": 0.55,
        "closing_price": None, "result": None, "quoted_ask": 0.40,
        "fill_contracts": 250.0, "placed_utc": "2026-08-21T09:42:00+00:00",
    }
    b.update(kw)
    return b


def _write(tmp_path, ledger, logs):
    proc = tmp_path / "data" / "processed"
    (proc / "matchweek_logs").mkdir(parents=True)
    (proc / "season_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    for name, data in logs.items():
        (proc / "matchweek_logs" / name).write_text(json.dumps(data), encoding="utf-8")


STAKE = {
    "job": "stake", "started_utc": "2026-08-21T09:42:32+00:00", "ok": True, "errors": [],
    "details": {
        "markets": 21, "fixtures": 7, "bet_window_days": 7, "score_matrices": 30,
        "planned": {"A_divergence_kelly": 0, "B_divergence_flat": 0, "C_model_kelly": 1, "D_parlay": 0},
        "placed": {"A_divergence_kelly": 0, "B_divergence_flat": 0, "C_model_kelly": 1, "D_parlay": 0},
        "fill_adjustments": [{"arm": "C_model_kelly", "bet": "X vs Y — Under 2.5 Goals",
                              "action": "dropped", "reason": "edge did not survive slippage"}],
        "edge_distribution": {"n": 60, "max": 0.03, "median": -0.025, "min": -0.08,
                              "count_over": {"0.020": 1, "0.050": 0}},
        "dry_run": False, "bets": {}, "errors": [],
    },
}
SETTLE = {
    "job": "settle", "started_utc": "2026-08-25T09:35:00+00:00", "ok": True, "errors": [],
    "details": {
        "results_seen": 5, "settled": 1, "season": [
            {"arm": "A_divergence_kelly", "label": "Divergence + quarter-Kelly", "bankroll": 10000,
             "exposure": 0, "equity": 10000, "settled_bets": 0, "voided_bets": 0, "open_bets": 0,
             "wins": 0, "win_rate": None, "total_staked": 0, "pnl": 0, "roi_pct": None, "clv_pct": None},
            {"arm": "B_divergence_flat", "label": "Divergence + flat 1%", "bankroll": 10000,
             "exposure": 0, "equity": 10000, "settled_bets": 0, "voided_bets": 0, "open_bets": 0,
             "wins": 0, "win_rate": None, "total_staked": 0, "pnl": 0, "roi_pct": None, "clv_pct": None},
            {"arm": "C_model_kelly", "label": "Model-only + quarter-Kelly", "bankroll": 9700,
             "exposure": 0, "equity": 9700, "settled_bets": 1, "voided_bets": 0, "open_bets": 0,
             "wins": 0, "win_rate": 0, "total_staked": 300, "pnl": -300, "roi_pct": -100, "clv_pct": -8.5},
            {"arm": "D_parlay", "label": "Parlay / SGP", "bankroll": 10000,
             "exposure": 0, "equity": 10000, "settled_bets": 0, "voided_bets": 0, "open_bets": 0,
             "wins": 0, "win_rate": None, "total_staked": 0, "pnl": 0, "roi_pct": None, "clv_pct": None},
        ],
    },
}
SNAPSHOT = {
    "job": "snapshot", "started_utc": "2026-08-23T14:15:00+00:00", "ok": True, "errors": [],
    "details": {"markets": 80, "stamped": 3,
                "edge_distribution": {"n": 80, "max": 0.012, "median": -0.026,
                                      "count_over": {"0.020": 0}}},
}


def test_builds_index_and_one_matchweek(tmp_path):
    led = _ledger(C_model_kelly={
        "bankroll": 9700.0,
        "history": [_bet(result="LOSS", pnl=-300.0, stake=300.0, price=0.30,
                         label="Deportivo vs Elche — Moneyline: Elche Win",
                         settled_utc="2026-08-25T09:35:10+00:00")],
    })
    _write(tmp_path, led, {"20260821T094232_stake.json": STAKE,
                           "20260823T141500_snapshot.json": SNAPSHOT,
                           "20260825T093500_settle.json": SETTLE})
    out = site.build_site(tmp_path, tmp_path / "docs")

    idx = (out / "index.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in idx
    assert "Divergence Lab" in idx
    assert "Season scoreboard" in idx
    assert "Data integrity" in idx
    assert "24 bets voided" in idx           # integrity note is always present
    assert "data through 2026-08-25" in idx  # tracks the latest log, not wall clock

    pages = sorted(p.name for p in out.glob("matchweek-*.html"))
    assert pages == ["matchweek-2026-08-17.html"]     # ISO-week Monday of the Aug 21 run
    wk = (out / pages[0]).read_text(encoding="utf-8")
    assert "Matchweek 1" in wk
    assert "Elche Win" in wk
    assert "LOST -300" in wk
    assert "edge did not survive slippage" in wk      # fill adjustment surfaced


def test_idempotent(tmp_path):
    _write(tmp_path, _ledger(), {"20260821T094232_stake.json": STAKE,
                                 "20260825T093500_settle.json": SETTLE})
    a = site.build_site(tmp_path, tmp_path / "d1")
    b = site.build_site(tmp_path, tmp_path / "d2")
    for name in sorted(p.name for p in a.glob("*.html")):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_empty_state_still_renders(tmp_path):
    (tmp_path / "data" / "processed" / "matchweek_logs").mkdir(parents=True)
    (tmp_path / "data" / "processed" / "season_ledger.json").write_text(
        json.dumps(_ledger()), encoding="utf-8")
    out = site.build_site(tmp_path, tmp_path / "docs")
    idx = (out / "index.html").read_text(encoding="utf-8")
    assert "No matchweeks staked yet." in idx
    assert list(out.glob("matchweek-*.html")) == []


def test_scoreboard_sorts_by_clv_nulls_last(tmp_path):
    _write(tmp_path, _ledger(), {"20260825T093500_settle.json": SETTLE})
    rows = site._scoreboard(SETTLE, _ledger())
    assert rows[0]["key"] == "C_model_kelly"          # only arm with a CLV number
    assert [r["clv"] for r in rows[1:]] == [None, None, None]


def test_dry_runs_are_ignored(tmp_path):
    dry = json.loads(json.dumps(STAKE))
    dry["details"]["dry_run"] = True
    _write(tmp_path, _ledger(), {"20260821T094232_stake.json": dry})
    out = site.build_site(tmp_path, tmp_path / "docs")
    assert list(out.glob("matchweek-*.html")) == []
    assert "No matchweeks staked yet." in (out / "index.html").read_text(encoding="utf-8")
