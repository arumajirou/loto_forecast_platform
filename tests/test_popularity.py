"""Conscious-selection avoidance: the only strategy with a measurable edge."""

import numpy as np
import pytest

from loto.game.geometry import geometry_for
from loto.strategy.popularity import (
    FEATURE_NAMES,
    combination_features,
    expected_value_ratio,
    fit_popularity,
    score_combinations,
    suggest_unpopular,
)

G = geometry_for("loto7")


def test_feature_vector_width_matches_names():
    assert combination_features([1, 2, 3, 4, 5, 6, 7], G).size == len(FEATURE_NAMES)


def test_calendar_bias_feature_separates_date_picks_from_high_numbers():
    dates = combination_features([3, 7, 12, 19, 24, 28, 31], G)
    highs = combination_features([32, 33, 34, 35, 36, 37, 20], G)
    i = FEATURE_NAMES.index("frac_calendar")
    assert dates[i] == 1.0
    assert highs[i] < dates[i]


def test_consecutive_run_feature_detects_a_straight():
    i = FEATURE_NAMES.index("consecutive_runs")
    assert combination_features([1, 2, 3, 4, 5, 6, 7], G)[i] == 1.0
    assert combination_features([1, 5, 11, 17, 23, 29, 35], G)[i] == 0.0


def test_wrong_width_is_rejected():
    with pytest.raises(ValueError, match="expected 7"):
        combination_features([1, 2, 3], G)


def _dataset(n=200, signal=True, seed=0):
    rng = np.random.default_rng(seed)
    combos, winners = [], []
    for _ in range(n):
        c = sorted(rng.choice(np.arange(1, 38), size=7, replace=False).tolist())
        f = combination_features(c, G)
        base = 3.0 + (4.0 * f[FEATURE_NAMES.index("frac_calendar")] if signal else 0.0)
        winners.append(max(rng.poisson(np.exp(base * 0.4)), 0))
        combos.append(c)
    return combos, winners


def test_detects_a_planted_popularity_signal():
    combos, winners = _dataset(signal=True, seed=1)
    model = fit_popularity(combos, winners, G, n_permutations=200)
    assert model.usable
    assert model.permutation_p_value < 0.05


def test_reports_no_signal_on_pure_noise_and_refuses_to_act():
    combos, winners = _dataset(signal=False, seed=2)
    model = fit_popularity(combos, winners, G, n_permutations=200)
    assert not model.usable
    assert suggest_unpopular(model, G) == []
    assert "do NOT act" in model.to_dict()["interpretation"]


def test_win_probability_is_reported_as_unimprovable():
    combos, winners = _dataset(signal=True, seed=3)
    model = fit_popularity(combos, winners, G, n_permutations=100)
    out = expected_value_ratio([1, 2, 3, 4, 5, 6, 7], model, G)
    assert out["win_probability"] == pytest.approx(1 / 10_295_472)
    assert "not improvable" in out["win_probability_note"]
    assert "does not make the bet +EV" in out["caveat"]


def test_suggestions_are_scored_and_ordered():
    combos, winners = _dataset(signal=True, seed=4)
    model = fit_popularity(combos, winners, G, n_permutations=100)
    picks = suggest_unpopular(model, G, n_suggestions=5, n_candidates=2000)
    assert len(picks) == 5
    scores = [p["predicted_log_cowinners"] for p in picks]
    assert scores == sorted(scores)
    for pick in picks:
        assert G.is_legal(pick["combination"])


def test_exclusions_are_respected():
    combos, winners = _dataset(signal=True, seed=5)
    model = fit_popularity(combos, winners, G, n_permutations=100)
    banned = [[1, 2, 3, 4, 5, 6, 7]]
    picks = suggest_unpopular(model, G, n_suggestions=3, n_candidates=1500, exclude=banned)
    assert all(p["combination"] != banned[0] for p in picks)


def test_sales_offset_is_recorded():
    combos, winners = _dataset(signal=True, seed=6)
    sales = np.full(len(combos), 1_000_000.0)
    model = fit_popularity(combos, winners, G, sales=sales, n_permutations=50)
    assert model.sales_adjusted is True


def test_non_positive_sales_are_rejected():
    combos, winners = _dataset(signal=True, seed=7)
    with pytest.raises(ValueError, match="strictly positive"):
        fit_popularity(combos, winners, G, sales=np.zeros(len(combos)), n_permutations=10)


def test_too_few_observations_is_rejected():
    combos, winners = _dataset(n=8, seed=8)
    with pytest.raises(ValueError, match="need more than"):
        fit_popularity(combos, winners, G, n_permutations=10)


def test_digit_games_are_out_of_scope_and_say_so():
    combos, winners = _dataset(signal=True, seed=9)
    model = fit_popularity(combos, winners, G, n_permutations=50)
    with pytest.raises(ValueError, match="select-family"):
        suggest_unpopular(model, geometry_for("numbers3"))


def test_scoring_is_vectorised_over_combinations():
    combos, winners = _dataset(signal=True, seed=10)
    model = fit_popularity(combos, winners, G, n_permutations=50)
    assert score_combinations(combos[:5], model, G).shape == (5,)
