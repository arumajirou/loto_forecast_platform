"""Leaderboard must refuse to invent a champion, and refuse cross-protocol ranking."""

import numpy as np
import pytest

from loto.evaluation.leaderboard import ModelResult, build_leaderboard, composite_score
from loto.evaluation.protocol import ProtocolMismatch

H = "a" * 64
H2 = "b" * 64


def _noise_results(n_models=12, n=100, seed=0):
    rng = np.random.default_rng(seed)
    out = [
        ModelResult("baseline", H, {"position_mae": 3.8}, rng.normal(3.8, 1.0, n), is_control=True)
    ]
    for i in range(n_models):
        out.append(ModelResult(f"m{i}", H, {"position_mae": 3.8}, rng.normal(3.8, 1.0, n)))
    return out


def test_no_champion_on_pure_noise():
    board = build_leaderboard(_noise_results(), baseline_model_id="baseline", n_boot=300)
    assert board.verdict == "NO_MODEL_BEATS_BASELINE"
    assert board.champion is None
    assert board.n_significant == 0


def test_every_row_reports_n_sd_and_adjusted_p():
    board = build_leaderboard(_noise_results(4), baseline_model_id="baseline", n_boot=200)
    for row in board.rows:
        assert row.n > 0 and row.sd >= 0.0
        assert 0.0 <= row.adjusted_p <= 1.0
        assert row.rank is not None


def test_genuine_winner_is_found_and_named():
    rng = np.random.default_rng(9)
    results = [
        ModelResult("baseline", H, {}, rng.normal(4.0, 0.5, 200), is_control=True),
        ModelResult("good", H, {}, rng.normal(3.0, 0.5, 200)),
        ModelResult("same", H, {}, rng.normal(4.0, 0.5, 200)),
    ]
    board = build_leaderboard(results, baseline_model_id="baseline", n_boot=600)
    assert board.verdict == "CANDIDATE_BEATS_BASELINE"
    assert board.champion is not None and board.champion.model_id == "good"


def test_cross_protocol_ranking_is_refused():
    rng = np.random.default_rng(1)
    results = [
        ModelResult("baseline", H, {}, rng.normal(size=50), is_control=True),
        ModelResult("other", H2, {}, rng.normal(size=50)),
    ]
    with pytest.raises(ProtocolMismatch):
        build_leaderboard(results, baseline_model_id="baseline")


def test_models_without_per_draw_losses_are_unranked_not_ranked():
    rng = np.random.default_rng(2)
    results = [
        ModelResult("baseline", H, {}, rng.normal(size=60), is_control=True),
        ModelResult("aggregate-only", H, {"position_mae": 0.1}, None),
    ]
    board = build_leaderboard(results, baseline_model_id="baseline", n_boot=200)
    assert board.unranked == ["aggregate-only"]
    assert board.champion is None


def test_missing_baseline_raises():
    with pytest.raises(KeyError, match="absent"):
        build_leaderboard(_noise_results(2), baseline_model_id="nope")


def test_baseline_without_losses_raises():
    results = [ModelResult("baseline", H, {}, None, is_control=True)]
    with pytest.raises(ValueError, match="per-draw"):
        build_leaderboard(results, baseline_model_id="baseline")


def test_composite_rejects_degenerate_ece_only_objective():
    """The v2.1.0 objective bug: weighting ece without sharpness rewards constants."""
    metrics = {"ece": 0.0, "mean_within_1": 0.28}
    with pytest.raises(ValueError, match="degenerate"):
        composite_score(metrics, {"ece": -0.05, "mean_within_1": 0.4})


def test_composite_accepts_ece_when_paired_with_sharpness():
    metrics = {"ece": 0.02, "brier": 0.15, "mean_within_1": 0.28}
    value = composite_score(metrics, {"ece": -0.05, "brier": -0.2, "mean_within_1": 0.4})
    assert isinstance(value, float)


def test_composite_rejects_unknown_metric():
    with pytest.raises(KeyError, match="absent metrics"):
        composite_score({"a": 1.0}, {"b": 1.0})
