"""Split conformal must deliver its advertised finite-sample coverage."""
import numpy as np
import pytest

from loto.evaluation.conformal import (
    adaptive_conformal,
    conformal_coverage,
    split_conformal,
    weighted_interval_score,
)


def test_marginal_coverage_meets_guarantee_on_iid_data():
    """The conformal guarantee is *marginal* over calibration draws.

    A single calibration split fluctuates by O(1/sqrt(n_cal)), so testing one split against
    0.90 is testing Monte Carlo noise. Averaging over independent splits tests the property
    that split conformal actually promises.
    """
    coverages = []
    for seed in range(30):
        rng = np.random.default_rng(seed)
        cal_a = rng.normal(size=300)
        test_a = rng.normal(size=300)
        interval = split_conformal(cal_a, np.zeros(300), np.zeros(300), alpha=0.1)
        coverages.append(conformal_coverage(test_a, interval)["coverage"])
    assert np.mean(coverages) >= 0.895


def test_single_split_coverage_is_close_to_target():
    rng = np.random.default_rng(0)
    interval = split_conformal(rng.normal(size=500), np.zeros(500), np.zeros(2000), alpha=0.1)
    cov = conformal_coverage(rng.normal(size=2000), interval)
    assert 0.84 <= cov["coverage"] <= 0.96
    assert cov["target"] == pytest.approx(0.9)


def test_guarantee_is_downgraded_honestly_when_calibration_is_tiny():
    """With n=3 you cannot certify 99% coverage; the reported guarantee must say so."""
    interval = split_conformal([1.0, 2.0, 3.0], [0.0, 0.0, 0.0], [0.0], alpha=0.01)
    assert interval.finite_sample_guarantee == pytest.approx(3 / 4)
    assert interval.finite_sample_guarantee < 0.99


def test_clipping_respects_the_game_value_range():
    interval = split_conformal([1.0, 40.0], [20.0, 20.0], [5.0], alpha=0.5, clip=(1.0, 37.0))
    assert interval.lower[0] >= 1.0 and interval.upper[0] <= 37.0
    assert interval.clipped_to == (1.0, 37.0)


def test_empty_calibration_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        split_conformal([], [], [1.0])


def test_alpha_out_of_range_is_rejected():
    with pytest.raises(ValueError, match="alpha"):
        split_conformal([1.0], [0.0], [0.0], alpha=1.0)


def test_adaptive_conformal_recovers_coverage_under_drift():
    rng = np.random.default_rng(3)
    n = 600
    actual = rng.normal(size=n) + np.linspace(0.0, 6.0, n)  # drifting mean
    predicted = np.zeros(n)
    out = adaptive_conformal(actual, predicted, alpha=0.1, gamma=0.05, warmup=50)
    assert out["coverage"] > 0.6  # fixed conformal collapses far below this
    assert out["n_evaluated"] == n - 50


def test_adaptive_conformal_needs_more_than_warmup():
    with pytest.raises(ValueError, match="warmup"):
        adaptive_conformal([1.0, 2.0], [0.0, 0.0], warmup=20)


def test_interval_score_penalises_both_directions():
    inside = weighted_interval_score([5.0], [4.0], [6.0], alpha=0.1)
    above = weighted_interval_score([9.0], [4.0], [6.0], alpha=0.1)
    below = weighted_interval_score([1.0], [4.0], [6.0], alpha=0.1)
    assert inside["interval_score"] < above["interval_score"]
    assert inside["interval_score"] < below["interval_score"]
    assert above["overprediction_penalty"] > 0 and below["underprediction_penalty"] > 0


def test_interval_score_cannot_be_gamed_by_widening():
    tight = weighted_interval_score(np.zeros(100), -np.ones(100), np.ones(100), alpha=0.1)
    wide = weighted_interval_score(np.zeros(100), -100 * np.ones(100), 100 * np.ones(100), alpha=0.1)
    assert wide["coverage"] == tight["coverage"] == 1.0
    assert wide["interval_score"] > tight["interval_score"]
