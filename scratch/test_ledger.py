"""Season ledger tests: accounting integrity and the never-silently-lose rule."""
import json
import pytest

from src.market import ledger
from src.market.grading import Bet, MatchResult, MARKET_1X2, MARKET_TOTALS, MARKET_CORNERS


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ledger, "LEDGER_PATH", str(tmp_path / "season_ledger.json"))
    monkeypatch.setattr(ledger, "ARCHIVE_PATH", str(tmp_path / "archive.json"))
    yield


def mk(sel="home", market=MARKET_1X2, stake=100.0, price=0.5, **kw):
    return Bet(market=market, selection=sel, home="liverpool", away="arsenal",
               stake=stake, price=price, **kw)


def test_fresh_ledger_has_four_arms_at_10k():
    s = ledger.load_state()
    assert set(s["arms"]) == set(ledger.ARMS)
    assert all(a["bankroll"] == 10_000.0 for a in s["arms"].values())
    assert sum(a["bankroll"] for a in s["arms"].values()) == 40_000.0


def test_place_debits_bankroll():
    ledger.place_bet("A_divergence_kelly", mk(stake=250.0))
    assert ledger.load_state()["arms"]["A_divergence_kelly"]["bankroll"] == 9750.0


def test_cannot_overstake_and_arms_are_never_reloaded():
    with pytest.raises(ledger.InsufficientBankroll):
        ledger.place_bet("A_divergence_kelly", mk(stake=10_001.0))
    assert ledger.load_state()["arms"]["A_divergence_kelly"]["bankroll"] == 10_000.0


def test_unknown_arm_rejected():
    with pytest.raises(ValueError):
        ledger.place_bet("E_nonexistent", mk())


def test_winning_bet_pays_stake_times_odds():
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0, price=0.5))   # 2.0x
    out = ledger.settle_match(MatchResult("liverpool", "arsenal", 2, 1))
    assert len(out["settled"]) == 1
    arm = ledger.load_state()["arms"]["A_divergence_kelly"]
    assert arm["bankroll"] == 10_100.0        # -100 stake, +200 payout
    assert arm["history"][0]["payout"] == 200.0
    assert arm["history"][0]["pnl"] == 100.0
    assert arm["active_bets"] == []


def test_losing_bet_keeps_stake_debited_once():
    ledger.place_bet("A_divergence_kelly", mk(sel="home", stake=100.0))
    ledger.settle_match(MatchResult("liverpool", "arsenal", 0, 1))
    arm = ledger.load_state()["arms"]["A_divergence_kelly"]
    assert arm["bankroll"] == 9900.0
    assert arm["history"][0]["pnl"] == -100.0


def test_no_double_counting_across_conservation():
    """Total equity must equal 40k plus net P&L at all times."""
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0, price=0.5))
    ledger.place_bet("B_divergence_flat", mk(sel="away", stake=200.0, price=0.25))
    ledger.settle_match(MatchResult("liverpool", "arsenal", 3, 0))
    summaries = ledger.season_summary()
    net_pnl = sum(s["pnl"] for s in summaries)
    equity = sum(s["equity"] for s in summaries)
    assert abs(equity - (40_000.0 + net_pnl)) < 1e-6


def test_bet_on_another_fixture_is_untouched():
    ledger.place_bet("A_divergence_kelly", mk())
    out = ledger.settle_match(MatchResult("chelsea", "everton", 1, 0))
    assert out["settled"] == []
    assert len(ledger.load_state()["arms"]["A_divergence_kelly"]["active_bets"]) == 1


def test_swapped_home_away_still_settles():
    ledger.place_bet("A_divergence_kelly", mk(sel="home", stake=100.0, price=0.5))
    ledger.settle_match(MatchResult("arsenal", "liverpool", 0, 2))   # Liverpool won away
    arm = ledger.load_state()["arms"]["A_divergence_kelly"]
    assert arm["history"][0]["result"] == "WIN"


# --- The rule that matters -------------------------------------------------

def test_ungradeable_bet_stays_pending_and_is_never_a_loss():
    ledger.place_bet("D_parlay", mk(market=MARKET_CORNERS, sel="over", line=9.5, stake=100.0))
    out = ledger.settle_match(MatchResult("liverpool", "arsenal", 1, 0))   # no corner data
    assert out["settled"] == []
    assert len(out["pending"]) == 1
    arm = ledger.load_state()["arms"]["D_parlay"]
    assert arm["history"] == []                  # not booked as a loss
    assert len(arm["active_bets"]) == 1
    assert arm["bankroll"] == 9900.0             # stake still held, not returned


def test_pending_bet_settles_once_data_arrives():
    ledger.place_bet("D_parlay", mk(market=MARKET_CORNERS, sel="over", line=9.5,
                                    stake=100.0, price=0.5))
    ledger.settle_match(MatchResult("liverpool", "arsenal", 1, 0))
    ledger.settle_match(MatchResult("liverpool", "arsenal", 1, 0, corners=12))
    arm = ledger.load_state()["arms"]["D_parlay"]
    assert arm["history"][0]["result"] == "WIN"
    assert arm["bankroll"] == 10_100.0


def test_push_stays_pending_rather_than_losing():
    ledger.place_bet("A_divergence_kelly", mk(market=MARKET_TOTALS, sel="over", line=3.0))
    out = ledger.settle_match(MatchResult("liverpool", "arsenal", 2, 1))
    assert len(out["pending"]) == 1
    assert ledger.load_state()["arms"]["A_divergence_kelly"]["history"] == []


# --- Reporting and safety ---------------------------------------------------

def test_clv_is_computed_from_closing_price():
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0, price=0.50, closing_price=0.55))
    ledger.settle_match(MatchResult("liverpool", "arsenal", 2, 1))
    assert ledger.arm_summary("A_divergence_kelly")["clv_pct"] == 10.0


def test_summary_reports_none_not_zero_when_no_bets():
    s = ledger.arm_summary("C_model_kelly")
    assert s["settled_bets"] == 0 and s["win_rate"] is None and s["roi_pct"] is None


def test_schema_mismatch_refuses_to_guess(tmp_path):
    with open(ledger.LEDGER_PATH, "w") as f:
        json.dump({"schema_version": 1, "arms": {}}, f)
    with pytest.raises(ValueError, match="schema"):
        ledger.load_state()


def test_archive_moves_legacy_ledger_aside(tmp_path):
    legacy = tmp_path / "paper_trading.json"
    legacy.write_text(json.dumps({"predict": {"magnus": {"bankroll": 812.5}}}))
    dest = ledger.archive_legacy_ledger(source=str(legacy))
    assert dest and not legacy.exists()
    archived = json.load(open(dest))
    assert archived["data"]["predict"]["magnus"]["bankroll"] == 812.5
    assert "archived_utc" in archived


def test_archive_is_a_noop_when_nothing_to_archive(tmp_path):
    assert ledger.archive_legacy_ledger(source=str(tmp_path / "nope.json")) is None


# --- Voids and closing prices ------------------------------------------------

def test_void_refunds_stake_and_excludes_from_metrics():
    ledger.place_bet("A_divergence_kelly", mk(stake=250.0))
    rec = ledger.void_bet("A_divergence_kelly", 0, "fixture postponed")
    assert rec["result"] == "VOID" and rec["pnl"] == 0.0
    s = ledger.arm_summary("A_divergence_kelly")
    assert s["bankroll"] == 10_000.0          # fully refunded
    assert s["settled_bets"] == 0             # excluded from the record
    assert s["voided_bets"] == 1
    assert s["roi_pct"] is None               # no staked volume to divide by


def test_void_does_not_drag_win_rate():
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0, price=0.5))
    ledger.settle_match(MatchResult("liverpool", "arsenal", 2, 1))   # a win
    ledger.place_bet("A_divergence_kelly", mk(sel="draw", stake=100.0))
    ledger.void_bet("A_divergence_kelly", 0, "market cancelled")
    s = ledger.arm_summary("A_divergence_kelly")
    assert s["settled_bets"] == 1 and s["win_rate"] == 100.0


def test_void_fixture_clears_every_arm():
    for arm in ("A_divergence_kelly", "B_divergence_flat", "C_model_kelly"):
        ledger.place_bet(arm, mk(stake=100.0))
    voided = ledger.void_fixture("liverpool", "arsenal", "postponed")
    assert len(voided) == 3
    st = ledger.load_state()
    assert all(st["arms"][a]["bankroll"] == 10_000.0 for a in
               ("A_divergence_kelly", "B_divergence_flat", "C_model_kelly"))


def test_void_fixture_ignores_other_matches():
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0))
    assert ledger.void_fixture("chelsea", "everton", "postponed") == []
    assert len(ledger.load_state()["arms"]["A_divergence_kelly"]["active_bets"]) == 1


def test_void_bad_index_raises():
    with pytest.raises(IndexError):
        ledger.void_bet("A_divergence_kelly", 0, "nothing there")


def test_record_closing_prices_stamps_active_bets():
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0, price=0.50))
    n = ledger.record_closing_prices(
        {("liverpool", "arsenal", MARKET_1X2, "home"): 0.58})
    assert n == 1
    bet = ledger.load_state()["arms"]["A_divergence_kelly"]["active_bets"][0]
    assert bet["closing_price"] == 0.58


def test_later_snapshot_overwrites_earlier():
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0, price=0.50))
    key = ("liverpool", "arsenal", MARKET_1X2, "home")
    ledger.record_closing_prices({key: 0.55})
    ledger.record_closing_prices({key: 0.61})
    assert ledger.load_state()["arms"]["A_divergence_kelly"]["active_bets"][0]["closing_price"] == 0.61


def test_closing_price_flows_into_clv_after_settlement():
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0, price=0.50))
    ledger.record_closing_prices({("liverpool", "arsenal", MARKET_1X2, "home"): 0.60})
    ledger.settle_match(MatchResult("liverpool", "arsenal", 2, 1))
    assert ledger.arm_summary("A_divergence_kelly")["clv_pct"] == pytest.approx(20.0)


def test_closing_price_not_stamped_after_kickoff():
    """
    A price observed after kickoff is an in-play price, not a closing price.

    Kalshi can leave a market open into the match, so without this guard the
    Saturday 11:00 snapshot would overwrite a Friday-night fixture's good
    Friday 18:00 stamp with a post-kickoff number and report it as the close.
    """
    from datetime import datetime, timedelta, timezone
    past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    ledger.place_bet("A_divergence_kelly", mk(stake=100.0, price=0.50, kickoff=past))
    key = ("liverpool", "arsenal", MARKET_1X2, "home")
    assert ledger.record_closing_prices({key: 0.58}) == 0
    bet = ledger.load_state()["arms"]["A_divergence_kelly"]["active_bets"][0]
    assert bet["closing_price"] is None


def test_final_pre_kickoff_price_survives_a_later_snapshot():
    """CLV is measured against the last price seen BEFORE kickoff, not the last seen."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    ledger.place_bet("A_divergence_kelly",
                     mk(stake=100.0, price=0.50,
                        kickoff=(now + timedelta(hours=2)).isoformat()))
    key = ("liverpool", "arsenal", MARKET_1X2, "home")
    ledger.record_closing_prices({key: 0.58})                          # pre-kickoff
    ledger.record_closing_prices({key: 0.99}, now=now + timedelta(hours=5))  # in-play
    bet = ledger.load_state()["arms"]["A_divergence_kelly"]["active_bets"][0]
    assert bet["closing_price"] == 0.58
