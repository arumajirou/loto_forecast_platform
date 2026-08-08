from __future__ import annotations

import copy

import numpy as np
import pytest
from pydantic import ValidationError

from loto.sktime_campaign.benchmark import (
    BaselineId,
    ValidationBenchmarkRequest,
    aggregate_seed_results,
    baseline_predictions,
    build_leaderboard,
    compute_metrics,
    data_contract,
    postprocess_predictions,
    run_validation_benchmark,
    split_views,
)


def payload() -> dict:
    values = [[float((row + col) % 10) for col in range(3)] for row in range(18)]
    return {
        "output_dir": "/tmp/out",
        "dataset": {
            "game_id": "numbers3",
            "draw_no": list(range(100, 118)),
            "position_names": ["N1", "N2", "N3"],
            "values": values,
            "legal_min": [0, 0, 0],
            "legal_max": [9, 9, 9],
        },
        "split": {"train_rows": 12, "validation_rows": 3, "holdout_rows": 3},
        "model_ids": [],
        "season_length": 3,
    }


def test_request_rejects_split_mismatch_and_draw_gaps() -> None:
    broken = payload()
    broken["split"]["holdout_rows"] = 2
    with pytest.raises(ValidationError):
        ValidationBenchmarkRequest.model_validate(broken)

    broken = payload()
    broken["dataset"]["draw_no"][5] += 2
    with pytest.raises(ValidationError):
        ValidationBenchmarkRequest.model_validate(broken)


def test_split_views_are_chronological_copies() -> None:
    request = ValidationBenchmarkRequest.model_validate(payload())
    views = split_views(request)
    assert views["train_draw_no"] == list(range(100, 112))
    assert views["validation_draw_no"] == [112, 113, 114]
    assert views["holdout_draw_no"] == [115, 116, 117]
    views["train"][0, 0] = 999
    assert request.dataset.values[0][0] != 999


def test_validation_contract_changes_holdout_hash_only_when_holdout_changes() -> None:
    first = ValidationBenchmarkRequest.model_validate(payload())
    changed_payload = copy.deepcopy(payload())
    changed_payload["dataset"]["values"][-1][0] = 9.0
    second = ValidationBenchmarkRequest.model_validate(changed_payload)
    first_contract = data_contract(first)
    second_contract = data_contract(second)
    assert first_contract["train_values_sha256"] == second_contract["train_values_sha256"]
    assert first_contract["validation_values_sha256"] == second_contract["validation_values_sha256"]
    assert first_contract["holdout_values_sha256"] != second_contract["holdout_values_sha256"]


def test_metrics_include_primary_and_position_scores() -> None:
    actual = np.asarray([[1, 5], [3, 9]], dtype=float)
    predicted = np.asarray([[2, 3], [1, 9]], dtype=float)
    metrics = compute_metrics(actual, predicted, position_names=["N1", "N2"])
    assert metrics["hit_at_1"] == 0.5
    assert metrics["position_hit_at_1"] == {"N1": 0.5, "N2": 0.5}
    assert metrics["all_position_hit_at_1"] == 0.0
    assert metrics["mae"] == 1.25
    assert metrics["mse"] == 2.25
    assert metrics["rmse"] == 1.5


def test_round_clip_postprocess() -> None:
    raw = np.asarray([[-1.2, 9.8], [4.6, 3.4]])
    result = postprocess_predictions(raw, legal_min=[0, 0], legal_max=[9, 9])
    assert result.tolist() == [[0.0, 9.0], [5.0, 3.0]]


@pytest.mark.parametrize("baseline_id", list(BaselineId))
def test_all_baselines_return_expected_shape(baseline_id: BaselineId) -> None:
    train = np.asarray(payload()["dataset"]["values"][:12], dtype=float)
    result = baseline_predictions(
        baseline_id,
        train=train,
        horizon=3,
        legal_min=[0, 0, 0],
        legal_max=[9, 9, 9],
        season_length=3,
        seed=1,
    )
    assert result.shape == (3, 3)
    assert np.isfinite(result).all()


def test_random_seed_aggregation_keeps_mean_variance_and_worst() -> None:
    rows = [
        {
            "candidate_id": "random_uniform",
            "candidate_kind": "baseline",
            "seed": seed,
            "status": "PASS",
            "metrics": {
                "hit_at_1": hit,
                "all_position_hit_at_1": 0.0,
                "mae": 2.0 + seed,
                "mse": 5.0 + seed,
                "rmse": 2.2 + seed,
            },
        }
        for seed, hit in [(1, 0.5), (2, 0.25), (3, 0.75)]
    ]
    aggregate = aggregate_seed_results(rows)[0]
    assert aggregate["metrics"]["hit_at_1"] == {
        "mean": 0.5,
        "variance": pytest.approx(1 / 24),
        "worst": 0.25,
    }
    assert aggregate["metrics"]["mae"]["worst"] == 5.0


def test_leaderboard_uses_hit_then_all_position_then_mae() -> None:
    aggregates = [
        {
            "candidate_id": "a",
            "status": "PASS",
            "metrics": {
                "hit_at_1": {"mean": 0.5},
                "all_position_hit_at_1": {"mean": 0.1},
                "mae": {"mean": 1.0},
            },
        },
        {
            "candidate_id": "b",
            "status": "PASS",
            "metrics": {
                "hit_at_1": {"mean": 0.5},
                "all_position_hit_at_1": {"mean": 0.2},
                "mae": {"mean": 2.0},
            },
        },
    ]
    assert [row["candidate_id"] for row in build_leaderboard(aggregates)] == [
        "b",
        "a",
    ]


def test_baseline_only_benchmark_is_pass_and_not_promoted() -> None:
    request = ValidationBenchmarkRequest.model_validate(payload())
    result = run_validation_benchmark(request)
    assert result["status"] == "PASS"
    assert result["promotion_status"] == "VALIDATION_ONLY_NOT_PROMOTED"
    assert result["best_validation_candidate"] is not None
    assert len(result["candidate_results"]) == len(BaselineId) + 2
