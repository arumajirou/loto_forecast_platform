from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.evaluation.metric_registry import (
    PRIMARY_METRIC_ID,
    REQUIRED_BASELINE_IDS,
    REQUIRED_POINT_METRICS,
    resolve_metric_id,
)
from loto.evaluation.protocol_diff import ProtocolComparisonRefused
from loto.evaluation.protocol_v2 import (
    BaselineManifest,
    EvaluationProtocolV2,
    GameGeometryIdentity,
    IdentityRef,
    MetricManifest,
    ResourceBudget,
    assert_protocols_comparable,
    compare_protocols,
    read_protocol_artifact,
    write_protocol_artifact,
)
from loto.evaluation.seed_summary import SeedMetricValue, summarize_seed_metric
from loto.evaluation.selection import CandidateMetrics, select_by_primary_metric

SHA = "a" * 64
GIT_SHA = "b" * 40


def _protocol(**updates: object) -> EvaluationProtocolV2:
    payload: dict[str, object] = {
        "game_geometry": GameGeometryIdentity(
            game="loto7",
            family="select",
            positions=7,
            universe_size=37,
            value_min=1,
            value_max=37,
            ascending=True,
        ),
        "data_snapshot": IdentityRef(identity="raw-001", sha256=SHA),
        "split_manifest": IdentityRef(identity="split-001", sha256=SHA),
        "feature_manifest": IdentityRef(identity="feature-001", sha256=SHA),
        "metric_manifest": MetricManifest(),
        "baseline_manifest": BaselineManifest(),
        "alpha": 0.05,
        "multiplicity_correction": "romano_wolf",
        "bootstrap_method": "paired_draw",
        "bootstrap_repetitions": 1000,
        "conformal_method": "split_conformal",
        "conformal_alpha": 0.1,
        "sentinel_inventory": ("permutation", "time_shift"),
        "sentinel_repetitions": 10,
        "post_processing_identity": IdentityRef(identity="round_clip", sha256=SHA),
        "reconciliation_identity": IdentityRef(identity="strict_ascending", sha256=SHA),
        "seed_inventory": (1, 42, 2026),
        "search_space_identity": IdentityRef(identity="search-v1", sha256=SHA),
        "resource_budget": ResourceBudget(
            cpu_count=8,
            gpu_count=1,
            gpu_memory_bytes=16_000_000_000,
            wall_time_seconds=3600,
            max_trials=20,
            parallel_trials=4,
        ),
        "package_versions": {"numpy": "2.0.0", "pydantic": "2.10.0"},
        "code_hash": SHA,
        "git_commit": GIT_SHA,
    }
    payload.update(updates)
    return EvaluationProtocolV2.model_validate(payload)


def test_canonical_metric_inventory_is_complete() -> None:
    assert REQUIRED_POINT_METRICS == (
        "hit_at_1",
        "position_hit_at_1",
        "all_positions_hit_at_1",
        "mae",
        "mse",
        "rmse",
    )


def test_protocol_v2_required_field_inventory_is_complete() -> None:
    required = {
        "schema_version",
        "game_geometry",
        "data_snapshot",
        "split_manifest",
        "feature_manifest",
        "metric_manifest",
        "baseline_manifest",
        "alpha",
        "multiplicity_correction",
        "bootstrap_method",
        "bootstrap_repetitions",
        "conformal_method",
        "conformal_alpha",
        "sentinel_inventory",
        "sentinel_repetitions",
        "post_processing_identity",
        "reconciliation_identity",
        "seed_inventory",
        "seed_aggregation_policy",
        "search_space_identity",
        "resource_budget",
        "package_versions",
        "code_hash",
        "git_commit",
    }
    assert required == set(EvaluationProtocolV2.model_fields)


def test_hit_at_1_is_primary() -> None:
    protocol = _protocol()
    assert PRIMARY_METRIC_ID == "hit_at_1"
    assert protocol.metric_manifest.primary_metric == "hit_at_1"


def test_better_mae_cannot_override_worse_hit_at_1() -> None:
    winner = select_by_primary_metric(
        [
            CandidateMetrics(
                "better-mae",
                {"hit_at_1": 0.40, "all_positions_hit_at_1": 0.1, "mae": 0.2, "rmse": 0.3},
            ),
            CandidateMetrics(
                "better-hit",
                {"hit_at_1": 0.60, "all_positions_hit_at_1": 0.2, "mae": 1.2, "rmse": 1.4},
            ),
        ]
    )
    assert winner.model_id == "better-hit"


@pytest.mark.parametrize("alias", ["within_1_rate", "element_within_1", "mean_within_1"])
def test_aliases_resolve_to_same_canonical_metric(alias: str) -> None:
    assert resolve_metric_id(alias) == "hit_at_1"


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("alpha", 0.01),
        ("multiplicity_correction", "holm"),
        ("conformal_alpha", 0.2),
    ],
)
def test_result_affecting_policy_change_changes_protocol_hash(
    field: str, replacement: object
) -> None:
    left = _protocol()
    right = left.model_copy(update={field: replacement})
    assert left.protocol_hash != right.protocol_hash


def test_baseline_inventory_change_changes_hash_and_missing_required_is_rejected() -> None:
    left = _protocol()
    right = _protocol(
        baseline_manifest={
            "baseline_ids": (*REQUIRED_BASELINE_IDS, "seasonal_naive"),
        }
    )
    assert left.protocol_hash != right.protocol_hash
    with pytest.raises(ValidationError):
        _protocol(baseline_manifest={"baseline_ids": REQUIRED_BASELINE_IDS[:-1]})


def test_seed_inventory_change_changes_hash() -> None:
    left = _protocol()
    right = left.model_copy(update={"seed_inventory": (1, 42, 1729, 2026)})
    assert left.protocol_hash != right.protocol_hash


def test_resource_budget_changes_budget_hash() -> None:
    left = _protocol()
    right = left.model_copy(
        update={
            "resource_budget": left.resource_budget.model_copy(update={"wall_time_seconds": 7200})
        }
    )
    assert left.comparison_budget_hash != right.comparison_budget_hash


def test_all_seed_mean_variance_and_worst_are_population_values() -> None:
    summary = summarize_seed_metric(
        "hit_at_1",
        [SeedMetricValue(1, 0.5), SeedMetricValue(42, 0.7), SeedMetricValue(2026, 0.9)],
        expected_seeds=(1, 42, 2026),
    )
    assert summary.count == 3
    assert summary.mean == pytest.approx(0.7)
    assert summary.population_variance == pytest.approx(0.02666666666666667)
    assert summary.standard_deviation == pytest.approx(math.sqrt(0.02666666666666667))
    assert summary.worst_value == pytest.approx(0.5)
    assert summary.worst_seed == 1


def test_worst_seed_respects_minimize_direction() -> None:
    summary = summarize_seed_metric(
        "mae",
        [SeedMetricValue(1, 0.5), SeedMetricValue(42, 1.2), SeedMetricValue(2026, 0.8)],
        expected_seeds=(1, 42, 2026),
    )
    assert summary.worst_value == pytest.approx(1.2)
    assert summary.worst_seed == 42


def test_best_seed_only_aggregation_is_rejected() -> None:
    with pytest.raises(ValueError, match="all approved seeds"):
        summarize_seed_metric(
            "hit_at_1",
            [SeedMetricValue(2026, 0.9)],
            expected_seeds=(1, 42, 2026),
        )


def test_v1_and_v2_are_readable_but_not_silently_comparable(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "protocol_hash": "legacy-hash",
                "protocol": {"schema_version": "1.0.0", "game": "loto7"},
            }
        ),
        encoding="utf-8",
    )
    legacy = read_protocol_artifact(path)
    current = _protocol()
    diff = compare_protocols(legacy, current)
    assert diff.comparable is False
    assert any(item.path == "schema_version" for item in diff.differences)
    with pytest.raises(ProtocolComparisonRefused):
        assert_protocols_comparable(legacy, current)


def test_v2_artifact_round_trip_preserves_hashes(tmp_path: Path) -> None:
    path = tmp_path / "protocol-v2.json"
    protocol = _protocol()
    write_protocol_artifact(path, protocol)
    payload = json.loads(path.read_text(encoding="utf-8"))
    loaded = read_protocol_artifact(path)
    assert isinstance(loaded, EvaluationProtocolV2)
    assert loaded.protocol_hash == protocol.protocol_hash
    assert payload["comparison_budget_hash"] == protocol.comparison_budget_hash


def test_historical_artifact_is_not_modified(tmp_path: Path) -> None:
    path = tmp_path / "protocol.json"
    original = b'{"schema_version":"1.0.0"}\n'
    path.write_bytes(original)
    with pytest.raises(FileExistsError):
        write_protocol_artifact(path, _protocol())
    assert path.read_bytes() == original


def test_protocol_diff_reports_field_path_values_and_severity() -> None:
    left = _protocol()
    right = left.model_copy(update={"alpha": 0.01})
    diff = compare_protocols(left, right)
    assert diff.comparable is False
    item = next(value for value in diff.differences if value.path == "alpha")
    assert item.left == 0.05
    assert item.right == 0.01
    assert item.severity.value == "RESULT_AFFECTING"
    with pytest.raises(ProtocolComparisonRefused):
        assert_protocols_comparable(left, right)


def test_unknown_field_nan_and_inf_are_rejected() -> None:
    payload = _protocol().model_dump(mode="python")
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        EvaluationProtocolV2.model_validate(payload)

    payload = _protocol().model_dump(mode="python")
    payload["alpha"] = float("nan")
    with pytest.raises(ValidationError):
        EvaluationProtocolV2.model_validate(payload)

    with pytest.raises(ValueError):
        select_by_primary_metric(
            [
                CandidateMetrics(
                    "bad",
                    {
                        "hit_at_1": float("inf"),
                        "all_positions_hit_at_1": 0.0,
                        "mae": 1.0,
                        "rmse": 1.0,
                    },
                )
            ]
        )
