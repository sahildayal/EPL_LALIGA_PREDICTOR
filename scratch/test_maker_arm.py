"""Arm E: resting limit orders, filled only when the tape trades through them."""
import copy
import json
from datetime import datetime, timezone

import pytest

from src.market import ledger
from src.market import maker_arm as E
from src.market.fees import maker_fee_as_fraction_of_payout
from src.pipeline.closer import held_kickoffs


@pytest.fixture(autouse=True)
def _tmp_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ledger, "LEDGER_PATH", str(tmp_path / "ledger.json"))


def _order(**kw):
    o = {"market": "1x2", "selection": "home", "home": "arsenal", "away": "chelsea",
         "line": None, "league": "epl", "kickoff": "2026-11-28T15:00:00Z",
         "ticker": "KXEPLGAME-26NOV28ARSCHE-ARS", "stake": 100.0, "limit": 0.48,
         "contracts": 208.3333, "fair_prob": 0.52, "net_edge": 0.0302,
         "quoted_bid": 0.47, "quoted_ask": 0.50, "label": "Arsenal vs Chelsea",
         "posted_utc": "2026-11-27T10:00:00+00:00"}
    o.update(kw)
    return o


def _trade(t, yes, taker="no"):
    return {"created_time": t, "yes_price_dollars": f"{yes:.4f}",
            "no_price_dollars": f"{1 - yes:.4f}", "taker_side": taker, "count_fp": "10"}


# --- limit price ----------------------------------------------------------------

def test_limit_improves_the_bid_by_a_cent_when_that_clears_the_bar():
    assert E.limit_price(fair=0.55, bid=0.47, ask=0.50) == 0.48


def test_limit_is_capped_so_the_edge_survives_the_maker_fee():
    price = E.limit_price(fair=0.52, bid=0.50, ask=0.53)
    assert price is not None
    assert 0.52 - price - maker_fee_as_fraction_of_payout(price) >= E.MIN_EDGE


def test_no_order_when_the_limit_would_cross_the_spread():
    # fair far above the market: bid+1c reaches the ask, which would be a taker trade
    assert E.limit_price(fair=0.90, bid=0.49, ask=0.50) is None


def test_no_order_outside_the_price_bounds():
    assert E.limit_price(fair=0.06, bid=0.02, ask=0.04) is None


# --- the fill rule (agreed 2026-11-22: strictly below our price) -----------------

def test_a_trade_at_our_price_is_not_a_fill():
    assert E.first_fill(_order(), [_trade("2026-11-27T12:00:00Z", 0.48)]) is None


def test_a_trade_below_our_price_is_a_fill():
    hit = E.first_fill(_order(), [_trade("2026-11-27T12:00:00Z", 0.47)])
    assert hit and hit[1] == pytest.approx(0.47)


def test_trades_before_posting_or_after_kickoff_do_not_count():
    trades = [_trade("2026-11-27T09:00:00Z", 0.40), _trade("2026-11-28T15:30:00Z", 0.30)]
    assert E.first_fill(_order(), trades) is None


def test_a_no_order_reads_the_no_price():
    o = _order(selection="not_home", limit=0.50)
    assert E.first_fill(o, [_trade("2026-11-27T12:00:00Z", yes=0.45)]) is None   # NO at 0.55
    assert E.first_fill(o, [_trade("2026-11-27T12:00:00Z", yes=0.52)]) is not None  # NO 0.48


# --- resolution -----------------------------------------------------------------

AFTER = datetime(2026, 11, 29, tzinfo=timezone.utc)


def test_filled_order_becomes_a_bet_at_the_limit_price():
    book = {"bankroll": 9900.0, "active_bets": [], "active_orders": [_order()]}
    out = E.resolve_orders(book, lambda *a: [_trade("2026-11-27T12:00:00Z", 0.46)], now=AFTER)
    assert len(out["filled"]) == 1 and book["active_orders"] == []
    [bet] = book["active_bets"]
    assert bet["price"] == 0.48 and bet["order_type"] == "maker"
    assert book["bankroll"] == 9900.0          # the stake stays committed to the bet


def test_unfilled_order_is_refunded_and_recorded():
    book = {"bankroll": 9900.0, "active_bets": [], "active_orders": [_order()]}
    out = E.resolve_orders(book, lambda *a: [], now=AFTER)
    assert len(out["unfilled"]) == 1 and book["bankroll"] == 10000.0
    assert book["order_history"][0]["status"] == "UNFILLED" and book["active_bets"] == []


def test_order_before_kickoff_is_left_alone():
    book = {"bankroll": 9900.0, "active_bets": [], "active_orders": [_order()]}
    E.resolve_orders(book, lambda *a: pytest.fail("tape read early"),
                     now=datetime(2026, 11, 28, 14, tzinfo=timezone.utc))
    assert len(book["active_orders"]) == 1


def test_unreadable_tape_keeps_the_order_open():
    book = {"bankroll": 9900.0, "active_bets": [], "active_orders": [_order()]}

    def boom(*a):
        raise RuntimeError("503")
    out = E.resolve_orders(book, boom, now=AFTER)
    assert out["errors"] and len(book["active_orders"]) == 1 and book["bankroll"] == 9900.0


# --- ledger ---------------------------------------------------------------------

def test_v3_ledger_migrates_to_v4_without_touching_existing_arms():
    s = ledger.new_state()
    v3 = copy.deepcopy(s)
    v3["schema_version"] = 3
    del v3["arms"]["E_maker_flat"]
    for book in v3["arms"].values():
        del book["active_orders"], book["order_history"]
    v3["arms"]["C_model_kelly"]["bankroll"] = 4307.99
    with open(ledger.LEDGER_PATH, "w") as f:
        json.dump(v3, f)
    s = ledger.load_state()
    assert s["schema_version"] == 4
    assert s["arms"]["E_maker_flat"]["bankroll"] == 10_000.0
    assert s["arms"]["C_model_kelly"]["bankroll"] == 4307.99
    assert s["migrations"][-1]["from"] == 3


def test_place_order_holds_the_stake_and_counts_as_exposure():
    ledger.place_order("E_maker_flat", _order())
    s = ledger.arm_summary("E_maker_flat")
    assert s["bankroll"] == 9900.0 and s["exposure"] == 100.0 and s["open_orders"] == 1


def test_closing_price_is_stamped_on_a_resting_order():
    state = ledger.load_state()
    state["arms"]["E_maker_flat"]["active_orders"].append(_order())
    key = ledger.closing_price_key("arsenal", "chelsea", "1x2", "home")
    ledger.record_closing_prices({key: 0.51}, state=state, bids={key: 0.49},
                                 now=datetime(2026, 11, 28, 14, 40, tzinfo=timezone.utc))
    o = state["arms"]["E_maker_flat"]["active_orders"][0]
    assert o["closing_price"] == 0.51 and o["closing_bid"] == 0.49


def test_closer_watches_resting_orders():
    state = {"arms": {"E_maker_flat": {"active_orders": [_order()]}}}
    assert len(held_kickoffs(state)) == 1


def test_plan_skips_markets_already_held_as_orders():
    mk = [{"home": "arsenal", "away": "chelsea", "market": "1x2", "selection": "home",
           "ask": 0.50, "bid": 0.47, "ticker": "T", "league": "epl",
           "kickoff": "2026-11-28T15:00:00Z"}]
    fair = {("arsenal", "chelsea"): {"1x2": {"home": 0.55, "draw": 0.25, "away": 0.20}}}
    book = {"bankroll": 10000.0, "starting_bankroll": 10000.0, "active_bets": [],
            "active_orders": []}
    [plan] = E.plan_orders(mk, fair, book)
    assert plan["order"]["limit"] == 0.48 and plan["order"]["stake"] == 100.0
    book["active_orders"].append(plan["order"])
    assert E.plan_orders(mk, fair, book) == []
