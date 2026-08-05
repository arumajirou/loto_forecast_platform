"""Deterministic PostgreSQL and MLflow registry snapshot comparisons."""

from __future__ import annotations

import math
from typing import Any

def _normalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _equal(left: Any, right: Any, tolerance: float) -> bool:
    left = _normalize(left)
    right = _normalize(right)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            float(left),
            float(right),
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
    return left == right


def _compare_record_maps(
    *,
    label: str,
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    compare_fields: tuple[str, ...],
    tolerance: float,
) -> list[str]:
    failures: list[str] = []
    expected_map = {
        tuple(_normalize(row.get(field)) for field in key_fields): row
        for row in expected
    }
    actual_map: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in actual:
        key = tuple(_normalize(row.get(field)) for field in key_fields)
        if key in actual_map:
            failures.append(f"{label} duplicate key: {key}")
            continue
        actual_map[key] = row
    for key in sorted(set(expected_map) - set(actual_map), key=str):
        failures.append(f"{label} missing key: {key}")
    for key in sorted(set(actual_map) - set(expected_map), key=str):
        failures.append(f"{label} unexpected key: {key}")
    for key in sorted(set(expected_map) & set(actual_map), key=str):
        expected_row = expected_map[key]
        actual_row = actual_map[key]
        for field in compare_fields:
            if not _equal(expected_row.get(field), actual_row.get(field), tolerance):
                failures.append(
                    f"{label} mismatch key={key} field={field}: "
                    f"expected={expected_row.get(field)!r}, "
                    f"actual={actual_row.get(field)!r}"
                )
    return failures


def _compare_postgres(
    expected: dict[str, Any],
    snapshot: dict[str, Any],
    tolerance: float,
) -> list[str]:
    failures: list[str] = []
    runs = snapshot.get("run_rows")
    if not isinstance(runs, list) or len(runs) != 1:
        failures.append(f"PostgreSQL expected one run row, found {len(runs or [])}")
        return failures
    run = runs[0]
    source = expected["source"]
    run_checks = {
        "registry_id": expected["registry_id"],
        "scoring_id": expected["scoring_id"],
        "registry_namespace": expected["registry_namespace"],
        "status": "PASS",
        "prediction_lock_sha256": source["prediction_lock_sha256"],
        "scoring_report_sha256": source["scoring_report_sha256"],
        "artifact_manifest_sha256": source["artifact_manifest_sha256"],
        "scoring_sha256s_sha256": source["scoring_sha256s_sha256"],
        "payload_sha256": expected["payload_sha256"],
        "mlflow_experiment": expected["backend_policy"]["mlflow_experiment"],
        "mlflow_parent_run_id": expected["receipt_mlflow_parent_run_id"],
    }
    for field, value in run_checks.items():
        if not _equal(value, run.get(field), tolerance):
            failures.append(
                f"PostgreSQL run mismatch field={field}: "
                f"expected={value!r}, actual={run.get(field)!r}"
            )
    failures.extend(
        _compare_record_maps(
            label="PostgreSQL candidates",
            expected=expected["candidates"],
            actual=list(snapshot.get("candidates") or []),
            key_fields=("candidate_key",),
            compare_fields=(
                "source_type",
                "model_name",
                "baseline_name",
                "track",
                "seed_count",
                "hit_pm1_mean",
                "hit_pm1_var",
                "hit_pm1_min",
                "hit_pm1_max",
                "all_positions_hit_pm1_mean",
                "mae_mean",
                "mse_mean",
                "rmse_mean",
                "worst_seed_hit_pm1",
                "rank",
            ),
            tolerance=tolerance,
        )
    )
    failures.extend(
        _compare_record_maps(
            label="PostgreSQL seed metrics",
            expected=expected["seed_metrics"],
            actual=list(snapshot.get("seed_metrics") or []),
            key_fields=("candidate_key", "seed_token"),
            compare_fields=(
                "seed",
                "hit_pm1",
                "all_positions_hit_pm1",
                "mae",
                "mse",
                "rmse",
            ),
            tolerance=tolerance,
        )
    )
    failures.extend(
        _compare_record_maps(
            label="PostgreSQL position metrics",
            expected=expected["position_metrics"],
            actual=list(snapshot.get("position_metrics") or []),
            key_fields=("row_key",),
            compare_fields=(
                "candidate_key",
                "seed_token",
                "unique_id",
                "variant",
                "hit_pm1",
                "exact_hit",
                "mae",
                "mse",
                "rmse",
            ),
            tolerance=tolerance,
        )
    )
    failures.extend(
        _compare_record_maps(
            label="PostgreSQL artifacts",
            expected=expected["artifacts"],
            actual=list(snapshot.get("artifacts") or []),
            key_fields=("path",),
            compare_fields=("size_bytes", "sha256"),
            tolerance=tolerance,
        )
    )
    return failures


def _compare_mlflow(
    expected: dict[str, Any],
    snapshot: dict[str, Any],
    tolerance: float,
    *,
    require_remote_artifacts: bool,
) -> list[str]:
    failures: list[str] = []
    parents = snapshot.get("parent_runs")
    if not isinstance(parents, list) or len(parents) != 1:
        failures.append(f"MLflow expected one parent run, found {len(parents or [])}")
        return failures
    parent = parents[0]
    expected_parent = expected["receipt_mlflow_parent_run_id"]
    if parent.get("run_id") != expected_parent:
        failures.append(
            "MLflow parent run ID differs from receipt: "
            f"expected={expected_parent}, actual={parent.get('run_id')}"
        )
    if parent.get("status") != "FINISHED":
        failures.append(f"MLflow parent run is not FINISHED: {parent.get('status')}")
    parent_tags = parent.get("tags") or {}
    parent_params = parent.get("params") or {}
    checks = {
        "registry_id": expected["registry_id"],
        "registry_role": "parent",
        "payload_sha256": expected["payload_sha256"],
        "scoring_id": expected["scoring_id"],
    }
    for field, value in checks.items():
        if parent_tags.get(field) != value:
            failures.append(
                f"MLflow parent tag mismatch {field}: "
                f"expected={value!r}, actual={parent_tags.get(field)!r}"
            )
    param_checks = {
        "registry_id": expected["registry_id"],
        "scoring_id": expected["scoring_id"],
        "registry_namespace": expected["registry_namespace"],
        "payload_sha256": expected["payload_sha256"],
        "priority_metric": "hit_pm1",
    }
    for field, value in param_checks.items():
        if str(parent_params.get(field)) != str(value):
            failures.append(
                f"MLflow parent param mismatch {field}: "
                f"expected={value!r}, actual={parent_params.get(field)!r}"
            )

    expected_children = {
        (str(row["candidate_key"]), str(row["seed_token"])): row
        for row in expected["seed_metrics"]
    }
    actual_children: dict[tuple[str, str], dict[str, Any]] = {}
    for child in list(snapshot.get("child_runs") or []):
        tags = child.get("tags") or {}
        key = (
            str(tags.get("candidate_key") or ""),
            str(tags.get("seed_token") or ""),
        )
        if key in actual_children:
            failures.append(f"MLflow duplicate child key: {key}")
        actual_children[key] = child
        if child.get("status") != "FINISHED":
            failures.append(f"MLflow child is not FINISHED: {key}")
        if tags.get("mlflow.parentRunId") != expected_parent:
            failures.append(f"MLflow child parent mismatch: {key}")
        if tags.get("payload_sha256") != expected["payload_sha256"]:
            failures.append(f"MLflow child payload SHA mismatch: {key}")
    for key in sorted(set(expected_children) - set(actual_children)):
        failures.append(f"MLflow child missing: {key}")
    for key in sorted(set(actual_children) - set(expected_children)):
        failures.append(f"MLflow unexpected child: {key}")
    for key in sorted(set(expected_children) & set(actual_children)):
        expected_row = expected_children[key]
        metrics = actual_children[key].get("metrics") or {}
        for field in ("hit_pm1", "all_positions_hit_pm1", "mae", "mse", "rmse"):
            expected_value = expected_row.get(field)
            if expected_value is None:
                continue
            if not _equal(expected_value, metrics.get(field), tolerance):
                failures.append(
                    f"MLflow child metric mismatch key={key} field={field}: "
                    f"expected={expected_value!r}, actual={metrics.get(field)!r}"
                )

    if require_remote_artifacts:
        failures.extend(
            _compare_record_maps(
                label="MLflow artifacts",
                expected=expected["mlflow_artifacts"],
                actual=list(snapshot.get("artifacts") or []),
                key_fields=("path",),
                compare_fields=("sha256",),
                tolerance=tolerance,
            )
        )
    return failures

