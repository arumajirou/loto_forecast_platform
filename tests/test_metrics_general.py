"""Metrics must work for every game, not just Loto7."""

import numpy as np
import pytest

from loto.evaluation.metrics_general import (
    evaluate_all,
    mase,
    positional_metrics,
    probabilistic_metrics,
    ranking_metrics,
    reliability_curve,
    set_overlap_metrics,
    smape,
)
from loto.game.geometry import geometry_for, known_games


@pytest.mark.parametrize("game", known_games())
def test_positional_metrics_accept_every_game_shape(game):
    g = geometry_for(game)
    rng = np.random.default_rng(0)
    actual = rng.integers(g.value_min, g.value_max + 1, size=(30, g.positions)).astype(float)
    out = positional_metrics(actual, actual, g)
    assert out["position_mae"] == 0.0
    assert out["exact_row_rate"] == 1.0
    assert out["positions"] == g.positions


def test_wrong_width_is_rejected_with_a_useful_message():
    g = geometry_for("loto6")
    with pytest.raises(ValueError, match="shape \\(n_draws, 6\\)"):
        positional_metrics(np.zeros((5, 7)), np.zeros((5, 7)), g)


def test_standard_error_is_reported():
    g = geometry_for("loto7")
    rng = np.random.default_rng(1)
    a = rng.integers(1, 38, size=(50, 7)).astype(float)
    b = rng.integers(1, 38, size=(50, 7)).astype(float)
    out = positional_metrics(a, b, g)
    assert out["position_mae_se"] > 0.0
    assert out["position_mae_se"] < out["position_mae_sd"]


def test_single_draw_has_zero_dispersion_not_nan():
    g = geometry_for("mini")
    out = positional_metrics(np.ones((1, 5)), np.ones((1, 5)), g)
    assert out["position_mae_sd"] == 0.0 and out["position_mae_se"] == 0.0


def test_set_overlap_only_applies_to_select_games():
    assert (
        set_overlap_metrics(np.ones((2, 3)), np.ones((2, 3)), geometry_for("numbers3"))[
            "set_overlap_supported"
        ]
        == 0.0
    )
    out = set_overlap_metrics(
        [[1, 2, 3, 4, 5, 6, 7]], [[1, 2, 3, 4, 5, 6, 7]], geometry_for("loto7")
    )
    assert out["mean_hits_at_7"] == 7.0 and out["jackpot_rate"] == 1.0


def test_expected_hits_reference_is_included():
    out = set_overlap_metrics(
        [[1, 2, 3, 4, 5, 6, 7]], [[8, 9, 10, 11, 12, 13, 14]], geometry_for("loto7")
    )
    assert out["mean_hits_at_7"] == 0.0
    assert out["expected_hits_uniform"] == pytest.approx(49 / 37)


def test_brier_skill_score_is_zero_for_the_uniform_predictor():
    g = geometry_for("loto7")
    rng = np.random.default_rng(2)
    targets = np.zeros((40, 37))
    for row in targets:
        row[rng.choice(37, size=7, replace=False)] = 1.0
    probs = np.full((40, 37), 7 / 37)
    out = probabilistic_metrics(targets, probs, g)
    assert out["brier_skill_score"] == pytest.approx(0.0, abs=1e-9)
    assert out["mass_error"] == pytest.approx(0.0, abs=1e-9)


def test_probabilistic_metrics_reject_out_of_range_probabilities():
    g = geometry_for("loto7")
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        probabilistic_metrics(np.zeros((2, 37)), np.full((2, 37), 1.5), g)


def test_mass_error_detects_an_illegal_probability_vector():
    g = geometry_for("loto7")
    out = probabilistic_metrics(np.zeros((2, 37)), np.full((2, 37), 0.5), g)
    assert out["mass_error"] > 10.0


def test_reliability_curve_covers_all_bins():
    curve = reliability_curve(np.array([0, 1, 0, 1]), np.array([0.1, 0.9, 0.2, 0.8]), bins=5)
    assert len(curve) == 5
    assert sum(row["count"] for row in curve) == 4


def test_ranking_metrics_perfect_ranking():
    g = geometry_for("loto7")
    targets = np.zeros((1, 37))
    targets[0, :7] = 1.0
    scores = np.linspace(1.0, 0.0, 37).reshape(1, -1)
    out = ranking_metrics(targets, scores, g)
    assert out["precision_at_7"] == 1.0 and out["ndcg_at_7"] == pytest.approx(1.0)


def test_mase_uses_the_seasonal_naive_denominator():
    insample = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert mase([6.0], [6.0], insample) == 0.0
    assert mase([6.0], [7.0], insample) == pytest.approx(1.0)


def test_mase_rejects_a_constant_series():
    with pytest.raises(ValueError, match="undefined"):
        mase([1.0], [1.0], np.ones(10))


def test_smape_handles_the_zero_denominator():
    assert smape([0.0], [0.0]) == 0.0
    assert smape([1.0], [1.0]) == 0.0


def test_evaluate_all_skips_probabilistic_when_absent():
    g = geometry_for("bingo5")
    a = np.tile(np.arange(1, 9, dtype=float), (5, 1))
    out = evaluate_all(a, a, g)
    assert "brier" not in out and out["position_mae"] == 0.0
