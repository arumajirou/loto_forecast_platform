import numpy as np

from loto.coverage.core import (
    evaluate_candidates,
    generate_candidate_pool,
    greedy_coverage_select,
    simultaneous_conformal_radius,
)


def test_evaluate_candidates_best_of_k():
    actual = [[1, 5, 10, 15, 20, 25, 30], [2, 6, 11, 16, 21, 26, 31]]
    candidates = [[1, 5, 10, 15, 20, 25, 30], [3, 7, 12, 17, 22, 27, 32]]
    result = evaluate_candidates(actual, candidates, tolerance=1)
    assert result.row_within_tolerance == 1.0
    assert result.exact_row_rate == 0.5


def test_simultaneous_conformal_radius():
    actual = [[1, 5, 10, 15, 20, 25, 30], [2, 6, 11, 16, 21, 26, 31]]
    predicted = [[1, 4, 10, 14, 20, 24, 30], [4, 6, 11, 16, 21, 26, 31]]
    assert simultaneous_conformal_radius(actual, predicted, coverage=0.5) >= 1


def test_generate_pool_is_legal():
    probs = np.full((7, 37), 1e-9)
    for i, center in enumerate([2, 7, 12, 17, 22, 27, 32]):
        probs[i, center - 1] = 1.0
        probs[i] /= probs[i].sum()
    pool = generate_candidate_pool(probs, per_position_top=3, beam_width=100, pool_size=20)
    assert pool
    assert all(len(row) == 7 and list(row) == sorted(set(row)) for row in pool)


def test_greedy_cover_selects_multiple_regions():
    actual = [[1, 5, 10, 15, 20, 25, 30], [10, 14, 18, 22, 26, 30, 34]]
    pool = [actual[0], actual[1]]
    selected, trace = greedy_coverage_select(
        actual, pool, target_coverage=1.0, tolerance=0, max_candidates=2
    )
    assert len(selected) == 2
    assert trace[-1]["coverage"] == 1.0


def test_catalog_position_models_are_routable():
    from loto.models.catalog import get_model_spec

    assert get_model_spec("ridge-position").task == "position_series"
    assert get_model_spec("mlforecast-ridge").task == "position_series"
