"""
Arm D: parlay pricing, settlement and the ways it could quietly lie.

The bugs worth testing for here are not crashes. They are prices that look
plausible and are wrong: an independence assumption applied to correlated legs,
a fee counted once instead of per leg, a parlay that keeps sitting open after a
leg has already lost.
"""
import numpy as np
import pytest

from src.market import ledger
from src.market.arms import ARM_D, plan_arm, place_arm
from src.market.grading import MatchResult
from src.market.parlay_arm import (
    LEG_SHRINKAGE, MAX_LEGS, SGP_PENALTY, SYNTHETIC_ASK_PENALTY,
    Parlay, ParlayLeg, enumerate_parlays, joint_from_score_matrix,
    legs_from_opportunities, price_parlay, select_parlays,
)
from src.models.implied_goals import score_matrix


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ledger, "LEDGER_PATH", str(tmp_path / "season_ledger.json"))
    yield


def leg(home="arsenal", away="chelsea", market="1x2", sel="home",
        fair=0.55, ask=0.45, line=None):
    return ParlayLeg(home=home, away=away, market=market, selection=sel,
                     fair_prob=fair, ask=ask, line=line)


def two_cross_game():
    return [leg(), leg(home="liverpool", away="everton", fair=0.60, ask=0.50)]


# --- Joint probability -------------------------------------------------------

def test_cross_game_legs_use_independence():
    p = price_parlay(two_cross_game())
    assert p["joint_method"] == "independent"
    assert not p["is_sgp"]


def test_same_game_legs_are_priced_off_the_score_matrix():
    m = score_matrix(1.7, 1.0)
    legs = [leg(sel="home", fair=0.55, ask=0.50),
            leg(market="totals", sel="over", line=2.5, fair=0.55, ask=0.50)]
    p = price_parlay(legs, {("arsenal", "chelsea"): m})
    assert p["is_sgp"] and p["joint_method"] == "score_matrix"


def test_same_game_correlation_is_not_the_product():
    """
    Home win and over 2.5 are positively correlated: a team that wins tends to
    have scored. Multiplying the two treats them as independent and understates
    the joint probability, which is the exact error a naive SGP makes.
    """
    m = score_matrix(1.9, 0.9)
    legs = [leg(sel="home"), leg(market="totals", sel="over", line=2.5)]
    exact = joint_from_score_matrix(legs, m)

    marginals = joint_from_score_matrix([legs[0]], m) * joint_from_score_matrix([legs[1]], m)
    assert exact > marginals
    assert abs(exact - marginals) > 0.02        # materially, not marginally


def test_mutually_exclusive_same_game_legs_price_near_zero():
    m = score_matrix(1.5, 1.2)
    legs = [leg(sel="home"), leg(market="btts", sel="no")]
    # Home win with BTTS no is possible (1-0), so this must be positive but small.
    j = joint_from_score_matrix(legs, m)
    assert 0.0 < j < joint_from_score_matrix([legs[0]], m)


def test_integer_totals_leg_excludes_the_push_region():
    """A 3.0 leg pushes on exactly 3 goals; the joint must renormalise over the rest."""
    m = score_matrix(1.6, 1.4)
    legs = [leg(sel="home"), leg(market="totals", sel="over", line=3.0)]
    j = joint_from_score_matrix(legs, m)
    n = m.shape[0]
    totals = np.add.outer(np.arange(n), np.arange(n))
    idx_h, idx_a = np.indices((n, n))
    raw = float(m[(idx_h > idx_a) & (totals > 3)].sum())
    assert j > raw                                 # conditioning on no push raises it


def test_sgp_without_a_matrix_refuses_to_price():
    """
    Falling back to multiplication for same-game legs is the single worst thing
    this module could do, so the absence of a matrix must mean no bet.
    """
    legs = [leg(sel="home"), leg(market="totals", sel="over", line=2.5)]
    assert price_parlay(legs, {}) is None
    assert price_parlay(legs, None) is None


def test_unsupported_market_in_an_sgp_refuses_rather_than_approximating():
    m = score_matrix(1.5, 1.2)
    legs = [leg(sel="home"),
            ParlayLeg(home="arsenal", away="chelsea", market="corners",
                      selection="over", fair_prob=0.5, ask=0.45, line=9.5)]
    assert price_parlay(legs, {("arsenal", "chelsea"): m}) is None


# --- Fees, penalties and shrinkage -------------------------------------------

def test_fees_are_charged_per_leg():
    """
    The compounding fee is the main reason parlays lose. A three-leg parlay must
    pay three fees against one payout, not one.
    """
    two = price_parlay(two_cross_game())
    three = price_parlay(two_cross_game() + [leg(home="tottenham", away="fulham",
                                                 fair=0.58, ask=0.48)])
    assert three["fee_frac"] > two["fee_frac"]


def test_legs_are_shrunk_toward_their_ask_before_compounding():
    """Guards the winner's-curse correction against being silently removed."""
    l1, l2 = two_cross_game()
    p = price_parlay([l1, l2])
    raw = l1.fair_prob * l2.fair_prob
    shrunk = ((l1.fair_prob - LEG_SHRINKAGE * (l1.fair_prob - l1.ask))
              * (l2.fair_prob - LEG_SHRINKAGE * (l2.fair_prob - l2.ask)))
    assert p["fair_prob"] == pytest.approx(shrunk)
    assert p["fair_prob"] < raw


def test_shrinkage_compounds_across_legs():
    """A per-leg bias becomes a larger bias on the product. That is the point."""
    legs2 = two_cross_game()
    legs3 = legs2 + [leg(home="tottenham", away="fulham", fair=0.58, ask=0.48)]
    raw2 = np.prod([l.fair_prob for l in legs2])
    raw3 = np.prod([l.fair_prob for l in legs3])
    gap2 = raw2 - price_parlay(legs2)["fair_prob"]
    gap3 = raw3 - price_parlay(legs3)["fair_prob"]
    assert gap3 / raw3 > gap2 / raw2


def test_correlated_sgp_legs_with_no_edge_produce_no_edge():
    """
    Regression, and the worst bug this module has had.

    Correlation raises the joint probability above the product of the marginals.
    An earlier version took that uplift in the numerator while leaving the ask at
    the plain product of leg asks — so BTTS-yes plus over-2.5 quoted at
    0.48 x 0.50 = 0.24 against a true joint of 0.41 showed an 11-point "edge"
    that was pure artefact. Arm D would have posted spectacular fake returns all
    season for a reason that has nothing to do with betting skill.

    Here every leg is priced exactly at fair, so there is no edge anywhere. The
    parlay must therefore show none either — after fees and penalties, strictly
    negative.
    """
    m = score_matrix(1.6, 1.3)
    btts = joint_from_score_matrix([leg(market="btts", sel="yes")], m)
    over = joint_from_score_matrix([leg(market="totals", sel="over", line=2.5)], m)
    legs = [leg(market="btts", sel="yes", fair=btts, ask=btts),
            leg(market="totals", sel="over", line=2.5, fair=over, ask=over)]

    p = price_parlay(legs, {("arsenal", "chelsea"): m})
    assert p is not None
    # The correlation uplift must appear on BOTH sides, so they cancel.
    assert p["ask"] == pytest.approx(p["fair_prob"], abs=1e-9)
    assert p["net_edge"] < 0                       # only fees and penalty remain
    # And it must be well above the naive product, which is the artefact price.
    assert p["ask"] > btts * over


def test_sgp_ask_carries_the_correlation_multiplier():
    m = score_matrix(1.7, 1.2)
    legs = [leg(market="btts", sel="yes", fair=0.55, ask=0.50),
            leg(market="totals", sel="over", line=2.5, fair=0.58, ask=0.52)]
    p = price_parlay(legs, {("arsenal", "chelsea"): m})
    exact = joint_from_score_matrix(legs, m)
    correlation = exact / (0.55 * 0.58)
    assert correlation > 1.0                       # these legs are correlated
    assert p["ask"] == pytest.approx(0.50 * 0.52 * correlation)


def test_genuine_per_leg_edge_still_compounds_in_an_sgp():
    """The fix must remove the artefact without removing the real signal."""
    m = score_matrix(1.7, 1.2)
    legs = [leg(market="btts", sel="yes", fair=0.60, ask=0.50),
            leg(market="totals", sel="over", line=2.5, fair=0.63, ask=0.52)]
    p = price_parlay(legs, {("arsenal", "chelsea"): m})
    assert p["fair_prob"] > p["ask"]               # real overlay survives
    assert p["net_edge"] > 0


def test_sgp_carries_an_extra_penalty():
    m = score_matrix(1.7, 1.0)
    sgp = price_parlay([leg(sel="home"), leg(market="totals", sel="over", line=2.5)],
                       {("arsenal", "chelsea"): m})
    assert sgp["penalty"] == pytest.approx(SYNTHETIC_ASK_PENALTY + SGP_PENALTY)
    assert price_parlay(two_cross_game())["penalty"] == pytest.approx(SYNTHETIC_ASK_PENALTY)


def test_ask_is_the_product_and_is_flagged_synthetic():
    p = price_parlay(two_cross_game())
    assert p["ask"] == pytest.approx(0.45 * 0.50)
    assert Parlay(legs=p["legs"], stake=100, ask=p["ask"]).ask_is_synthetic


# --- Structural refusals -----------------------------------------------------

def test_two_legs_on_the_same_fixture_and_market_are_rejected():
    """Home and away on one match cannot both win; nor can over and under."""
    assert price_parlay([leg(sel="home"), leg(sel="away")]) is None


def test_leg_count_is_bounded():
    assert price_parlay([leg()]) is None
    too_many = [leg(home=f"t{i}a", away=f"t{i}b") for i in range(MAX_LEGS + 1)]
    assert price_parlay(too_many) is None


def test_enumeration_is_capped():
    """
    The cap is a bias defence, not a speed guard: the more combinations we rank,
    the more the winner is chosen on estimation error.
    """
    legs = [leg(home=f"t{i}a", away=f"t{i}b", fair=0.70, ask=0.40) for i in range(30)]
    out = enumerate_parlays(legs, max_candidates=50)
    assert len(out) <= 50


def test_selection_refuses_overlapping_parlays():
    """Two parlays sharing a leg are one bet with extra steps."""
    shared = leg(home="arsenal", away="chelsea", fair=0.70, ask=0.40)
    a = price_parlay([shared, leg(home="a", away="b", fair=0.70, ask=0.40)])
    b = price_parlay([shared, leg(home="c", away="d", fair=0.70, ask=0.40)])
    chosen = select_parlays([a, b], max_parlays=3)
    assert len(chosen) == 1


def test_selection_sorts_by_net_edge():
    strong = price_parlay([leg(home="a", away="b", fair=0.80, ask=0.40),
                           leg(home="c", away="d", fair=0.80, ask=0.40)])
    weak = price_parlay([leg(home="e", away="f", fair=0.52, ask=0.50),
                         leg(home="g", away="h", fair=0.52, ask=0.50)])
    out = enumerate_parlays(strong["legs"] + weak["legs"], min_edge=-1.0)
    assert out[0]["net_edge"] >= out[-1]["net_edge"]


# --- Ledger integration ------------------------------------------------------

def _place(stake=100.0):
    p = price_parlay(two_cross_game())
    parlay = Parlay(legs=p["legs"], stake=stake, fair_prob=p["fair_prob"],
                    ask=p["ask"], net_edge=p["net_edge"])
    ledger.place_parlay(ARM_D, parlay)
    return parlay


def test_placing_a_parlay_debits_once():
    _place(100.0)
    book = ledger.load_state()["arms"][ARM_D]
    assert book["bankroll"] == pytest.approx(9900.0)
    assert len(book["active_parlays"]) == 1


def test_parlay_dies_on_its_first_losing_leg():
    """
    Once a leg loses the wager is worthless. Holding it open would overstate
    open exposure and push the loss into the wrong matchweek.
    """
    _place()
    ledger.settle_match(MatchResult(home="arsenal", away="chelsea",
                                    home_goals=0, away_goals=2))
    book = ledger.load_state()["arms"][ARM_D]
    assert book["active_parlays"] == []
    assert book["parlay_history"][0]["result"] == "LOSS"
    assert book["parlay_history"][0]["payout"] == 0.0
    assert book["bankroll"] == pytest.approx(9900.0)      # no refund on a loss


def test_parlay_stays_open_until_every_leg_is_in():
    _place()
    ledger.settle_match(MatchResult(home="arsenal", away="chelsea",
                                    home_goals=2, away_goals=0))
    book = ledger.load_state()["arms"][ARM_D]
    assert len(book["active_parlays"]) == 1
    assert book["active_parlays"][0]["legs"][0]["result"] == "WIN"
    assert book["active_parlays"][0]["legs"][1]["result"] is None


def test_parlay_pays_the_combined_price_when_every_leg_wins():
    parlay = _place(100.0)
    ledger.settle_match(MatchResult(home="arsenal", away="chelsea",
                                    home_goals=2, away_goals=0))
    ledger.settle_match(MatchResult(home="liverpool", away="everton",
                                    home_goals=3, away_goals=1))
    book = ledger.load_state()["arms"][ARM_D]
    record = book["parlay_history"][0]
    assert record["result"] == "WIN"
    assert record["payout"] == pytest.approx(100.0 / (0.45 * 0.50), abs=0.01)
    assert book["active_parlays"] == []


def test_ungradeable_leg_leaves_the_parlay_open():
    """The old grader's cardinal sin was resolving the unknown as a loss."""
    legs = [leg(market="totals", sel="over", line=2.0),
            leg(home="liverpool", away="everton", fair=0.6, ask=0.5)]
    p = price_parlay(legs)
    ledger.place_parlay(ARM_D, Parlay(legs=p["legs"], stake=100.0,
                                      fair_prob=p["fair_prob"], ask=p["ask"]))
    out = ledger.settle_match(MatchResult(home="arsenal", away="chelsea",
                                          home_goals=1, away_goals=1))   # push
    assert out["parlays_pending"]
    assert len(ledger.load_state()["arms"][ARM_D]["active_parlays"]) == 1


def test_voiding_a_fixture_refunds_the_whole_parlay():
    _place(100.0)
    ledger.void_fixture("arsenal", "chelsea", "postponed")
    book = ledger.load_state()["arms"][ARM_D]
    assert book["bankroll"] == pytest.approx(10_000.0)
    assert book["parlay_history"][0]["result"] == "VOID"
    assert book["active_parlays"] == []


def test_voided_parlay_is_excluded_from_roi_and_win_rate():
    _place(100.0)
    ledger.void_fixture("arsenal", "chelsea", "postponed")
    s = ledger.arm_summary(ARM_D)
    assert s["settled_bets"] == 0 and s["voided_bets"] == 1
    assert s["roi_pct"] is None and s["win_rate"] is None


def test_parlay_counts_toward_the_arm_summary():
    parlay = _place(100.0)
    ledger.settle_match(MatchResult(home="arsenal", away="chelsea",
                                    home_goals=0, away_goals=2))
    s = ledger.arm_summary(ARM_D)
    assert s["settled_bets"] == 1 and s["settled_parlays"] == 1
    assert s["pnl"] == pytest.approx(-100.0)
    assert s["total_staked"] == pytest.approx(100.0)


def test_open_parlay_counts_as_exposure():
    _place(250.0)
    s = ledger.arm_summary(ARM_D)
    assert s["exposure"] == pytest.approx(250.0)
    assert s["equity"] == pytest.approx(10_000.0)
    assert s["open_parlays"] == 1


def test_parlay_clv_needs_every_leg_priced():
    """A half-stamped parlay would compare entry legs against closing legs."""
    _place(100.0)
    ledger.record_closing_prices({("arsenal", "chelsea", "1x2", "home"): 0.40})
    assert "closing_price" not in ledger.load_state()["arms"][ARM_D]["active_parlays"][0]

    ledger.record_closing_prices({("arsenal", "chelsea", "1x2", "home"): 0.40,
                                  ("liverpool", "everton", "1x2", "home"): 0.45})
    rec = ledger.load_state()["arms"][ARM_D]["active_parlays"][0]
    assert rec["closing_price"] == pytest.approx(0.40 * 0.45)


# --- Arm wiring --------------------------------------------------------------

def kmkt(home, away, sel="home", ask=0.40, market="1x2", **kw):
    return {"home": home, "away": away, "market": market, "selection": sel,
            "ask": ask, "league": "epl", **kw}


def test_arm_d_plans_parlays_not_singles():
    markets = [kmkt("arsenal", "chelsea"), kmkt("liverpool", "everton"),
               kmkt("tottenham", "fulham")]
    fair = {("arsenal", "chelsea"): {"1x2": {"home": 0.62}},
            ("liverpool", "everton"): {"1x2": {"home": 0.60}},
            ("tottenham", "fulham"): {"1x2": {"home": 0.58}}}
    plans = plan_arm(ARM_D, markets, fair)
    assert plans
    assert all("parlay" in p and "bet" not in p for p in plans)
    assert all(len(p["parlay"].legs) >= 2 for p in plans)


def test_arm_d_stakes_flat_not_kelly():
    """
    Kelly is superlinearly sensitive to an overstated probability, and a parlay's
    probability is a product of estimates each carrying its own error.
    """
    markets = [kmkt("arsenal", "chelsea", ask=0.30), kmkt("liverpool", "everton", ask=0.30)]
    fair = {("arsenal", "chelsea"): {"1x2": {"home": 0.80}},
            ("liverpool", "everton"): {"1x2": {"home": 0.80}}}
    plans = plan_arm(ARM_D, markets, fair)
    assert plans
    assert all(p["parlay"].stake == 100.0 for p in plans)      # 1% of $10,000


def test_arm_d_bets_nothing_without_enough_legs():
    fair = {("arsenal", "chelsea"): {"1x2": {"home": 0.62}}}
    assert plan_arm(ARM_D, [kmkt("arsenal", "chelsea")], fair) == []


def test_arm_d_place_writes_parlays_to_the_ledger():
    markets = [kmkt("arsenal", "chelsea"), kmkt("liverpool", "everton"),
               kmkt("tottenham", "fulham")]
    fair = {("arsenal", "chelsea"): {"1x2": {"home": 0.62}},
            ("liverpool", "everton"): {"1x2": {"home": 0.60}},
            ("tottenham", "fulham"): {"1x2": {"home": 0.58}}}
    plans = plan_arm(ARM_D, markets, fair)
    res = place_arm(ARM_D, plans)
    book = ledger.load_state()["arms"][ARM_D]
    assert len(res["placed"]) == len(plans)
    assert len(book["active_parlays"]) == len(plans)
    assert book["bankroll"] < 10_000.0


def test_arm_d_never_reloads_on_exhaustion():
    state = ledger.load_state()
    state["arms"][ARM_D]["bankroll"] = 10.0
    ledger.save_state(state)
    p = price_parlay(two_cross_game())
    parlay = Parlay(legs=p["legs"], stake=500.0, fair_prob=p["fair_prob"], ask=p["ask"])
    res = place_arm(ARM_D, [{"parlay": parlay}])
    assert res["placed"] == [] and len(res["skipped"]) == 1
    assert ledger.load_state()["arms"][ARM_D]["bankroll"] == 10.0


# --- Schema ------------------------------------------------------------------

def test_v2_ledger_migrates_additively(tmp_path):
    import json
    legacy = {
        "schema_version": 2, "season": "2026-27", "created_utc": "x",
        "arms": {k: {"label": v, "bankroll": 9500.0, "starting_bankroll": 10000.0,
                     "active_bets": [], "history": [{"result": "WIN", "stake": 100.0,
                                                     "pnl": 50.0, "price": 0.5}]}
                 for k, v in ledger.ARMS.items()},
    }
    with open(ledger.LEDGER_PATH, "w") as f:
        json.dump(legacy, f)

    state = ledger.load_state()
    assert state["schema_version"] == ledger.SCHEMA_VERSION
    for book in state["arms"].values():
        assert book["active_parlays"] == [] and book["parlay_history"] == []
        # Existing rows must be untouched: a migration that rewrites settled
        # bets would let the season's record be revised after the fact.
        assert book["history"][0]["pnl"] == 50.0
        assert book["bankroll"] == 9500.0


def test_unknown_schema_still_refuses():
    import json
    with open(ledger.LEDGER_PATH, "w") as f:
        json.dump({"schema_version": 99, "arms": {}}, f)
    with pytest.raises(ValueError, match="no additive migration"):
        ledger.load_state()
