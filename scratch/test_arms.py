"""Edge and arm tests — the layer that decides what money goes where."""
import pytest

from src.market import ledger
from src.market.arms import (
    ARM_A, ARM_B, ARM_C, ARM_D, ARM_CONFIGS, plan_arm, place_arm, plan_all,
)
from src.market.edge import (
    Opportunity, build_opportunities, filter_bettable, deduplicate_by_fixture,
    summarise, SOURCE_SHARP, SOURCE_MODEL,
)


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ledger, "LEDGER_PATH", str(tmp_path / "season_ledger.json"))
    yield


def mkt(sel="home", ask=0.40, market="1x2", home="arsenal", away="chelsea", **kw):
    return {"home": home, "away": away, "market": market,
            "selection": sel, "ask": ask, "league": "epl", **kw}


FAIR = {("arsenal", "chelsea"): {"1x2": {"home": 0.55, "draw": 0.25, "away": 0.20}}}


# --- Edge -------------------------------------------------------------------

def test_net_edge_subtracts_fees():
    o = Opportunity("arsenal", "chelsea", "1x2", "home", 0.55, 0.40, SOURCE_SHARP)
    assert o.gross_edge == pytest.approx(0.15)
    assert o.net_edge < o.gross_edge
    assert o.fee_frac > 0


def test_opportunity_built_from_sharp_line():
    opps = build_opportunities([mkt()], FAIR)
    assert len(opps) == 1 and opps[0].fair_source == SOURCE_SHARP
    assert opps[0].fair_prob == 0.55


def test_model_priced_requires_opt_in():
    model = {("arsenal", "chelsea"): {"1x2": {"home": 0.60}}}
    assert build_opportunities([mkt()], {}, model, allow_model_priced=False) == []
    opts = build_opportunities([mkt()], {}, model, allow_model_priced=True)
    assert len(opts) == 1 and opts[0].fair_source == SOURCE_MODEL


def test_sharp_line_preferred_over_model():
    model = {("arsenal", "chelsea"): {"1x2": {"home": 0.90}}}
    o = build_opportunities([mkt()], FAIR, model, allow_model_priced=True)[0]
    assert o.fair_source == SOURCE_SHARP and o.fair_prob == 0.55


def test_invalid_prices_are_dropped():
    for bad in (0.0, 1.0, None, "x"):
        assert build_opportunities([mkt(ask=bad)], FAIR) == []


def test_missing_fair_value_is_skipped():
    assert build_opportunities([mkt(home="everton", away="fulham")], FAIR) == []


def test_filter_applies_min_edge_after_fees():
    # 2c gross at 40c does not survive fees
    assert filter_bettable(build_opportunities([mkt(ask=0.53)], FAIR)) == []
    assert len(filter_bettable(build_opportunities([mkt(ask=0.40)], FAIR))) == 1


def test_filter_rejects_extreme_prices():
    fair = {("a", "b"): {"1x2": {"home": 0.99}}}
    o = build_opportunities([mkt(ask=0.02, home="a", away="b")], fair)
    assert filter_bettable(o) == []          # below min_ask, fees dominate


def test_filter_sorts_by_net_edge():
    fair = {("a", "b"): {"1x2": {"home": 0.60}}, ("c", "d"): {"1x2": {"home": 0.90}}}
    o = build_opportunities([mkt(home="a", away="b", ask=0.50),
                             mkt(home="c", away="d", ask=0.50)], fair)
    out = filter_bettable(o)
    assert out[0].net_edge > out[1].net_edge


def test_deduplicate_keeps_best_per_fixture_market():
    fair = {("arsenal", "chelsea"): {"1x2": {"home": 0.55, "draw": 0.40}}}
    o = build_opportunities([mkt("home", 0.40), mkt("draw", 0.20)], fair)
    out = deduplicate_by_fixture(filter_bettable(o))
    assert len(out) == 1
    assert out[0].selection == "draw"        # bigger net edge


def test_summarise_counts_sources():
    o = build_opportunities([mkt()], FAIR)
    s = summarise(o)
    assert s["n"] == 1 and s["sharp_priced"] == 1 and s["model_priced"] == 0
    assert summarise([])["n"] == 0


# --- Arms -------------------------------------------------------------------

def test_arm_a_stakes_proportionally_to_edge():
    plans = plan_arm(ARM_A, [mkt(ask=0.40)], FAIR)
    assert len(plans) == 1
    sp = plans[0]["stake_plan"]
    assert sp.should_bet and sp.stake > 0 and sp.fraction <= 0.03


def test_arm_b_stakes_flat_regardless_of_edge():
    small = plan_arm(ARM_B, [mkt(ask=0.48)], FAIR)
    big = plan_arm(ARM_B, [mkt(ask=0.20)], FAIR)
    assert small[0]["stake_plan"].stake == big[0]["stake_plan"].stake == 100.0


def test_arm_c_prices_off_the_model_even_when_a_sharp_line_exists():
    """
    Regression: arm C previously selected only opportunities where NO sharp line
    existed. Every market in scope always has one, so arm C would have placed
    zero bets all season and the control would have produced no data.
    """
    model = {("arsenal", "chelsea"): {"1x2": {"home": 0.62}}}
    plans = plan_arm(ARM_C, [mkt(ask=0.40)], FAIR, model_probs=model)
    assert len(plans) == 1
    assert plans[0]["opportunity"].fair_source == SOURCE_MODEL
    assert plans[0]["opportunity"].fair_prob == 0.62      # model, not the 0.55 sharp


def test_arm_c_bets_nothing_without_model_probabilities():
    assert plan_arm(ARM_C, [mkt(ask=0.40)], FAIR, model_probs={}) == []


def test_arm_c_and_arm_a_see_the_same_fixtures():
    """The arms must differ in fair value only, not in which matches they consider."""
    model = {("arsenal", "chelsea"): {"1x2": {"home": 0.62}}}
    a = plan_arm(ARM_A, [mkt(ask=0.40)], FAIR, model_probs=model)
    c = plan_arm(ARM_C, [mkt(ask=0.40)], FAIR, model_probs=model)
    assert a and c
    assert (a[0]["bet"].home, a[0]["bet"].away) == (c[0]["bet"].home, c[0]["bet"].away)
    assert a[0]["opportunity"].fair_prob != c[0]["opportunity"].fair_prob


def test_arm_c_has_a_wider_threshold_than_arm_a():
    assert ARM_CONFIGS[ARM_C].min_edge > ARM_CONFIGS[ARM_A].min_edge


def test_no_bet_when_edge_below_threshold():
    assert plan_arm(ARM_A, [mkt(ask=0.54)], FAIR) == []


def test_bankroll_reserved_across_multiple_bets():
    """A matchweek must not commit the same dollar twice."""
    fair, markets = {}, []
    for i in range(8):
        h, a = f"team{i}a", f"team{i}b"
        fair[(h, a)] = {"1x2": {"home": 0.70}}
        markets.append(mkt(home=h, away=a, ask=0.40))
    plans = plan_arm(ARM_A, markets, fair)
    total = sum(p["stake_plan"].stake for p in plans)
    assert total <= 10_000.0


def test_max_bets_caps_exposure():
    fair, markets = {}, []
    for i in range(30):
        h, a = f"t{i}a", f"t{i}b"
        fair[(h, a)] = {"1x2": {"home": 0.70}}
        markets.append(mkt(home=h, away=a, ask=0.40))
    assert len(plan_arm(ARM_A, markets, fair, max_bets=5)) <= 5


def test_place_arm_writes_to_ledger_and_debits():
    plans = plan_arm(ARM_A, [mkt(ask=0.40)], FAIR)
    res = place_arm(ARM_A, plans)
    assert len(res["placed"]) == 1
    book = ledger.load_state()["arms"][ARM_A]
    assert book["bankroll"] < 10_000.0
    assert len(book["active_bets"]) == 1


def test_place_arm_stops_rather_than_reloading_on_exhaustion():
    state = ledger.load_state()
    state["arms"][ARM_A]["bankroll"] = 10.0
    ledger.save_state(state)
    plans = plan_arm(ARM_A, [mkt(ask=0.40)], FAIR)
    for p in plans:
        p["bet"].stake = 500.0                     # force an over-stake
    res = place_arm(ARM_A, plans)
    assert res["placed"] == [] and len(res["skipped"]) == 1
    assert ledger.load_state()["arms"][ARM_A]["bankroll"] == 10.0


def test_plan_all_covers_every_funded_arm():
    """
    All four arms are funded, so all four must be planned. Arm D was omitted
    here originally, which would have left $10,000 idle all season and produced
    an empty column in the comparison the season exists to make.
    """
    from src.market.arms import ARM_D
    plans = plan_all([mkt(ask=0.40)], FAIR)
    assert set(plans) == {ARM_A, ARM_B, ARM_C, ARM_D}


def test_arms_a_and_b_pick_the_same_bet_but_size_differently():
    """The only difference between A and B must be the stake."""
    a = plan_arm(ARM_A, [mkt(ask=0.40)], FAIR)
    b = plan_arm(ARM_B, [mkt(ask=0.40)], FAIR)
    assert a[0]["bet"].selection == b[0]["bet"].selection
    assert a[0]["stake_plan"].stake != b[0]["stake_plan"].stake


# --- Derived markets carry extra uncertainty --------------------------------

from src.market.edge import SOURCE_DERIVED, DERIVATION_PENALTY

DERIVED_FAIR = {("arsenal", "chelsea"): {"btts": {"yes": 0.60}, "_btts_derived": True}}


def test_derived_btts_is_flagged():
    o = build_opportunities([mkt(sel="yes", market="btts", ask=0.45)], DERIVED_FAIR)[0]
    assert o.fair_source == SOURCE_DERIVED and o.is_derived


def test_derived_market_edge_is_penalised():
    """
    A grid over every (lambda, rho) triple reproducing a sharp line found the
    implied BTTS spanning ~0.011. That ambiguity belongs in the threshold.
    """
    o = build_opportunities([mkt(sel="yes", market="btts", ask=0.45)], DERIVED_FAIR)[0]
    direct = {("arsenal", "chelsea"): {"btts": {"yes": 0.60}}}
    d = build_opportunities([mkt(sel="yes", market="btts", ask=0.45)], direct)[0]
    assert o.net_edge == pytest.approx(d.net_edge - DERIVATION_PENALTY)
    assert not d.is_derived


def test_directly_priced_market_has_no_penalty():
    o = build_opportunities([mkt(ask=0.40)], FAIR)[0]
    assert o.derivation_penalty == 0.0
