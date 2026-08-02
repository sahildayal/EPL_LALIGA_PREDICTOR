"""Dixon-Coles tests, including the silent-fallback behaviour this replaces."""
import numpy as np
import pytest

from src.models.dixon_coles import DixonColes, TeamNotFitted, elo_priors


def synthetic_league(n_teams=10, rounds=6, seed=0):
    """
    Generates a league where team strength is known, so we can check the model
    actually recovers it rather than merely producing plausible numbers.
    """
    rng = np.random.default_rng(seed)
    teams = [f"team{i:02d}" for i in range(n_teams)]
    # team00 strongest, team09 weakest
    attack = np.linspace(0.45, -0.45, n_teams)
    defence = np.linspace(-0.35, 0.35, n_teams) + np.log(1.35)
    home, away, hg, ag, days = [], [], [], [], []
    day = rounds * n_teams * 4
    for _ in range(rounds):
        for i in range(n_teams):
            for j in range(n_teams):
                if i == j:
                    continue
                lam = np.exp(attack[i] + defence[j] + 0.25)
                mu = np.exp(attack[j] + defence[i])
                home.append(teams[i]); away.append(teams[j])
                hg.append(rng.poisson(lam)); ag.append(rng.poisson(mu))
                days.append(day)
                day -= 1
    return teams, home, away, hg, ag, days


@pytest.fixture(scope="module")
def fitted():
    teams, h, a, hg, ag, d = synthetic_league()
    return DixonColes(halflife_days=3650).fit(h, a, hg, ag, d), teams


def test_fit_converges(fitted):
    model, _ = fitted
    assert model.is_fitted and model.converged


def test_recovers_known_strength_ordering(fitted):
    """team00 was built strongest; its attack rating must come out on top."""
    model, teams = fitted
    order = [t for t, _ in sorted(zip(model.teams, model.attack), key=lambda x: -x[1])]
    assert order[0] == "team00"
    assert order[-1] == "team09"


def test_attack_sums_to_zero(fitted):
    model, _ = fitted
    assert abs(model.attack.sum()) < 1e-6


def test_home_advantage_is_positive(fitted):
    model, _ = fitted
    assert 0.05 < model.home_adv < 0.6


def test_strong_beats_weak_at_home(fitted):
    model, _ = fitted
    p = model.predict_one("team00", "team09")
    assert p[0] > 0.6 and p[0] > p[2]


def test_home_advantage_is_visible_in_reversed_fixture(fitted):
    model, _ = fitted
    home = model.predict_one("team04", "team05")
    away = model.predict_one("team05", "team04")
    assert home[0] > away[2]           # same pairing, home side always favoured


def test_probabilities_are_valid(fitted):
    model, _ = fitted
    p = model.predict_proba([("team01", "team07"), ("team03", "team02")])
    assert p.shape == (2, 3)
    assert np.allclose(p.sum(axis=1), 1.0)
    assert (p > 0).all()


def test_score_matrix_normalised(fitted):
    model, _ = fitted
    assert abs(model.score_matrix("team02", "team06").sum() - 1.0) < 1e-9


def test_derived_markets_are_coherent(fitted):
    """Markets come off one score matrix, so they must not contradict each other."""
    model, _ = fitted
    m = model.market_probs("team02", "team06")
    assert abs(m["home"] + m["draw"] + m["away"] - 1.0) < 1e-9
    assert abs(m["btts_yes"] + m["btts_no"] - 1.0) < 1e-9
    assert m["over_1.5"] > m["over_2.5"] > m["over_3.5"]


# --- The behaviour this replaces --------------------------------------------

def test_unknown_team_raises_instead_of_returning_uniform(fitted):
    """
    The old model returned 0.33/0.33/0.34 for any unseen team, which is how
    every club match ended up with an identical prediction.
    """
    model, _ = fitted
    with pytest.raises(TeamNotFitted):
        model.predict_one("newly promoted fc", "team00")


def test_prior_lets_a_promoted_team_be_predicted(fitted):
    model, _ = fitted
    priors = {"newly promoted fc": (-0.4, 0.4)}      # weak attack, leaky defence
    p = model.predict_one("team00", "newly promoted fc", priors=priors)
    assert p[0] > 0.65                               # strong home side dominates
    assert np.isclose(p.sum(), 1.0)


def test_elo_priors_rank_teams_correctly():
    ratings = {"strong": 1900.0, "mid": 1700.0, "weak": 1500.0}
    priors = elo_priors(["strong", "mid", "weak"], ratings)
    assert priors["strong"][0] > priors["mid"][0] > priors["weak"][0]
    assert priors["strong"][1] < priors["weak"][1]          # defence sign flipped
    assert abs(priors["mid"][0]) < 1e-9                      # mid is the centre


def test_elo_priors_empty_when_no_ratings():
    assert elo_priors(["a", "b"], {}) == {}


def test_unfitted_model_raises(fitted):
    with pytest.raises(TeamNotFitted):
        DixonColes().predict_one("a", "b")


def test_insufficient_data_raises():
    with pytest.raises(ValueError):
        DixonColes().fit(["a"], ["b"], [1], [0], [0])


def test_time_decay_favours_recent_form():
    """Recent results must dominate when the half-life is short."""
    teams = ["a", "b"]
    # 'a' dominated long ago; 'b' has dominated recently.
    home = ["a"] * 30 + ["b"] * 30
    away = ["b"] * 30 + ["a"] * 30
    hg = [4] * 30 + [4] * 30
    ag = [0] * 30 + [0] * 30
    days = list(range(700, 670, -1)) + list(range(30, 0, -1))

    recent = DixonColes(halflife_days=60).fit(home, away, hg, ag, days)
    assert recent.attack[recent.index["b"]] > recent.attack[recent.index["a"]]
