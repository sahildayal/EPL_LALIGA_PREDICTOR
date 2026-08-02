"""Tests for recovering goal expectations from sharp prices."""
import numpy as np
import pytest

from src.models.implied_goals import (
    score_matrix, markets_from_matrix, solve_lambdas, derive_markets,
)


def test_matrix_is_a_distribution():
    m = score_matrix(1.5, 1.2)
    assert abs(m.sum() - 1.0) < 1e-9
    assert (m > 0).all()


def test_markets_are_internally_coherent():
    m = markets_from_matrix(score_matrix(1.6, 1.1))
    assert abs(m["home"] + m["draw"] + m["away"] - 1.0) < 1e-9
    assert abs(m["btts_yes"] + m["btts_no"] - 1.0) < 1e-9
    assert m["over_0.5"] > m["over_1.5"] > m["over_2.5"] > m["over_3.5"]


def test_higher_lambdas_mean_more_goals_and_more_btts():
    low = markets_from_matrix(score_matrix(0.9, 0.8))
    high = markets_from_matrix(score_matrix(2.2, 1.9))
    assert high["over_2.5"] > low["over_2.5"]
    assert high["btts_yes"] > low["btts_yes"]


def test_recovers_lambdas_it_generated():
    """Round trip: known lambdas -> probabilities -> solver -> same lambdas."""
    true_h, true_a = 1.7, 1.05
    m = markets_from_matrix(score_matrix(true_h, true_a))
    lam_h, lam_a, diag = solve_lambdas(
        {"home": m["home"], "draw": m["draw"], "away": m["away"]},
        {"over": m["over_2.5"]})
    assert lam_h == pytest.approx(true_h, abs=0.05)
    assert lam_a == pytest.approx(true_a, abs=0.05)
    assert diag["max_error"] < 0.005


def test_recovered_btts_matches_the_truth():
    true_h, true_a = 1.4, 1.3
    truth = markets_from_matrix(score_matrix(true_h, true_a))
    got = derive_markets({"home": truth["home"], "draw": truth["draw"],
                          "away": truth["away"]}, {"over": truth["over_2.5"]})
    assert got
    assert got["btts_yes"] == pytest.approx(truth["btts_yes"], abs=0.01)


def test_realistic_sharp_line_produces_sane_btts():
    """A real Pinnacle-shaped favourite line should give a plausible BTTS."""
    got = derive_markets({"home": 0.55, "draw": 0.25, "away": 0.20}, {"over": 0.55})
    assert got
    assert 0.35 < got["btts_yes"] < 0.75
    assert 1.0 < got["lambda_home"] < 3.0
    assert 0.4 < got["lambda_away"] < 2.0


def test_heavy_favourite_gives_low_btts():
    fav = derive_markets({"home": 0.84, "draw": 0.11, "away": 0.05}, {"over": 0.60})
    even = derive_markets({"home": 0.40, "draw": 0.28, "away": 0.32}, {"over": 0.52})
    assert fav and even
    assert fav["btts_yes"] < even["btts_yes"]


def test_refuses_to_derive_without_a_totals_line():
    """
    1X2 prices constrain the balance between the sides but barely constrain the
    goal LEVEL, and BTTS is driven mainly by the total. With rho free the solver
    reproduces 1X2 exactly at wildly different totals, so the derived BTTS would
    be arbitrary. Returning nothing is the honest answer.
    """
    assert derive_markets({"home": 0.50, "draw": 0.27, "away": 0.23}) == {}
    assert derive_markets({"home": 0.50, "draw": 0.27, "away": 0.23}, {}) == {}


def test_rho_is_fitted_and_lands_in_the_football_range():
    got = derive_markets({"home": 0.45, "draw": 0.27, "away": 0.28}, {"over": 0.55})
    assert got
    assert -0.25 <= got["rho"] <= 0.0
    assert got["fit_max_error"] < 0.005


def test_bad_fit_returns_nothing_rather_than_a_wrong_price():
    """
    Incoherent inputs must yield {} , not a confident-looking BTTS. A derived
    price from lambdas that don't reproduce the sharp 1X2 is not sharp-anchored,
    and would silently become a model-priced bet inside a divergence arm.
    """
    impossible = {"home": 0.98, "draw": 0.01, "away": 0.01}
    assert derive_markets(impossible, {"over": 0.02}, max_error=0.005) == {}


def test_missing_1x2_key_raises():
    with pytest.raises(ValueError):
        solve_lambdas({"home": 0.5, "draw": 0.3})


def test_fit_diagnostics_are_reported():
    _, _, diag = solve_lambdas({"home": 0.45, "draw": 0.27, "away": 0.28}, {"over": 0.53})
    assert "max_error" in diag and "errors" in diag and diag["converged"]


def test_totals_line_is_respected():
    """The solver must hit the supplied over probability, not a default."""
    got = derive_markets({"home": 0.45, "draw": 0.27, "away": 0.28}, {"over": 0.62})
    assert got
    assert got["over_2.5"] == pytest.approx(0.62, abs=0.02)


# --- Asian totals lines ------------------------------------------------------

from src.models.implied_goals import over_probability


def test_half_line_is_plain_threshold():
    m = score_matrix(1.5, 1.2)
    assert over_probability(m, 2.5) == pytest.approx(markets_from_matrix(m)["over_2.5"])


def test_integer_line_conditions_on_no_push():
    """At a 3.0 line, exactly 3 goals is a push; the quoted pair excludes it."""
    m = score_matrix(1.6, 1.4)
    n = m.shape[0]
    totals = np.add.outer(np.arange(n), np.arange(n))
    push = m[totals == 3].sum()
    raw_over = m[totals > 3].sum()
    assert push > 0.10                                    # pushes are common
    assert over_probability(m, 3.0) == pytest.approx(raw_over / (1 - push))
    assert over_probability(m, 3.0) > raw_over            # conditioning raises it


def test_quarter_line_is_the_average_of_its_halves():
    m = score_matrix(1.6, 1.4)
    expected = 0.5 * over_probability(m, 2.5) + 0.5 * over_probability(m, 3.0)
    assert over_probability(m, 2.75) == pytest.approx(expected)


def test_over_probability_decreases_with_the_line():
    m = score_matrix(1.6, 1.4)
    vals = [over_probability(m, l) for l in (1.5, 2.0, 2.5, 2.75, 3.0, 3.5)]
    assert all(a >= b for a, b in zip(vals, vals[1:]))


def test_unsupported_line_raises_rather_than_being_ignored():
    with pytest.raises(ValueError):
        over_probability(score_matrix(1.5, 1.2), 2.3)


def test_asian_line_actually_constrains_the_solve():
    """
    Regression. The solver previously built over_{line} keys only for
    0.5/1.5/2.5/3.5 and skipped the constraint via `if over_key in m`, leaving
    the goal level free. Arsenal v Coventry (84% favourite, Over 3.0 at 0.497)
    solved to lambda 3.61/0.97 and BTTS 0.612 instead of 2.67/0.48 and 0.351 —
    a 26-point mispricing that looked entirely plausible.
    """
    fav = {"home": 0.84, "draw": 0.11, "away": 0.05}
    got = derive_markets(fav, {"over": 0.497}, totals_line=3.0)
    assert got
    assert got["fit_max_error"] < 0.01
    assert 2.2 < got["lambda_home"] < 3.2
    assert 0.3 < got["lambda_away"] < 0.7
    assert 0.25 < got["btts_yes"] < 0.45


def test_btts_rises_with_the_totals_line():
    fav = {"home": 0.84, "draw": 0.11, "away": 0.05}
    b = [derive_markets(fav, {"over": 0.50}, totals_line=l)["btts_yes"]
         for l in (2.5, 2.75, 3.0)]
    assert b[0] < b[1] < b[2]


def test_unsupported_line_refuses_the_whole_derivation():
    with pytest.raises(ValueError):
        solve_lambdas({"home": 0.45, "draw": 0.27, "away": 0.28},
                      {"over": 0.5}, totals_line=2.3)
