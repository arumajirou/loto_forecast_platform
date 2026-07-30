import numpy as np

from loto.evaluation.metrics import brier_score, evaluate_draws, paired_draw_bootstrap


def test_hits_at_7_and_position_metrics_are_computed_per_draw():
    actual = np.array([[1, 4, 9, 15, 22, 30, 37], [2, 5, 10, 16, 23, 31, 36]])
    pred = np.array([[1, 4, 8, 14, 22, 29, 37], [1, 5, 11, 16, 24, 31, 35]])
    report = evaluate_draws(actual, pred)
    assert report["mean_hits_at_7"] == 3.5
    assert 0 <= report["within_1_rate"] <= 1


def test_brier_uniform_probability_is_finite():
    y = np.array([[1] * 7 + [0] * 30])
    p = np.full_like(y, 7 / 37, dtype=float)
    assert 0 < brier_score(y, p) < 1


def test_paired_bootstrap_resamples_draws_not_flat_positions():
    a = np.array([1.0, 0.0, 1.0, 0.0])
    b = np.array([0.0, 0.0, 0.0, 0.0])
    result = paired_draw_bootstrap(a, b, n_boot=500, seed=7)
    assert result["n_draws"] == 4
    assert result["diff"] == 0.5
