"""Fail-closed verification for integrated API coverage artifacts.

The verifier extends the existing campaign verification without changing its
legacy task and model-bundle checks. It validates the integrated root manifest,
the nested coverage-state bundle, portable SHA-256 manifests, and the explicit
GPU ``EXECUTION_PENDING`` boundary used while the target runtime is unavailable.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from .coverage_state import VerificationStatus
from .persistence import verify_sha256s, write_json, write_sha256s

_ROOT_REQUIRED_FILES = {
    "API_ARGUMENT_COVERAGE_PLAN.parquet",
    "API_ARGUMENT_COVERAGE_RESULT.csv",
    "API_ARGUMENT_COVERAGE_RESULT.parquet",
    "failures.json",
    "manifest.json",
    "SHA256SUMS",
}

_COVERAGE_REQUIRED_FILES = {
    "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.json",
    "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.csv",
    "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.parquet",
    "API_ARGUMENT_COVERAGE_RESOLVED.json",
    "API_ARGUMENT_COVERAGE_RESOLVED.csv",
    "API_ARGUMENT_COVERAGE_RESOLVED.parquet",
    "COVERAGE_SUMMARY.json",
    "manifest.json",
    "SHA256SUMS",
}

_NONFAILED_STATES = {
    VerificationStatus.EXECUTION_PENDING.value,
    VerificationStatus.PARTIALLY_VERIFIED.value,
    VerificationStatus.VERIFIED.value,
}


def _json_object(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"{label} missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label} unreadable: {path}: {type(exc).__name__}: {exc}")
        return {}
    if not isinstance(payload, dict):
        failures.append(f"{label} must be a JSON object: {path}")
        return {}
    if not payload:
        failures.append(f"{label} must not be empty: {path}")
    return payload


def _json_list(path: Path, failures: list[str], label: str) -> list[Any]:
    if not path.is_file():
        failures.append(f"{label} missing: {path}")
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label} unreadable: {path}: {type(exc).__name__}: {exc}")
        return []
    if not isinstance(payload, list):
        failures.append(f"{label} must be a JSON list: {path}")
        return []
    if not payload:
        failures.append(f"{label} must not be empty: {path}")
    return payload


def _safe_relative_path(
    run_root: Path,
    raw_path: Any,
    failures: list[str],
) -> Path | None:
    value = str(raw_path or "").strip()
    if not value:
        failures.append("coverage_state_path missing")
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        failures.append(f"unsafe coverage_state_path: {value}")
        return None
    resolved_root = run_root.resolve()
    resolved = (run_root / relative).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        failures.append(f"coverage_state_path escapes run root: {value}")
        return None
    return resolved


def _require_files(root: Path, expected: set[str], failures: list[str], label: str) -> None:
    for name in sorted(expected):
        if not (root / name).is_file():
            failures.append(f"{label} missing required file: {name}")


def _validate_count_map(
    value: Any,
    expected_total: int,
    failures: list[str],
    label: str,
) -> None:
    if not isinstance(value, Mapping):
        failures.append(f"{label} must be an object")
        return
    try:
        total = sum(int(count) for count in value.values())
    except (TypeError, ValueError):
        failures.append(f"{label} contains a non-integer count")
        return
    if total != expected_total:
        failures.append(f"{label} total mismatch: expected={expected_total}, actual={total}")


def _validate_failure_mode(
    run_root: Path,
    manifest: Mapping[str, Any],
    embedded: Mapping[str, Any],
    resolved_artifact: Path | None,
    failures: list[str],
) -> dict[str, Any]:
    coverage_root = run_root / "coverage-state"
    failure_path = run_root / "coverage_state_failure.json"
    if manifest.get("status") != "PARTIAL":
        failures.append("FAILED coverage state requires root status=PARTIAL")
    if str(manifest.get("coverage_state_path")) != "coverage_state_failure.json":
        failures.append("FAILED coverage state must point to coverage_state_failure.json")
    if coverage_root.exists():
        failures.append("partial coverage-state directory retained after resolver failure")

    failure = _json_object(failure_path, failures, "coverage-state failure evidence")
    if failure.get("status") != VerificationStatus.FAILED.value:
        failures.append("coverage-state failure evidence status must be FAILED")
    if failure.get("failed_phase") != "coverage_state_resolution":
        failures.append("coverage-state failure evidence has invalid failed_phase")
    if failure.get("gpu_runtime_status") != VerificationStatus.EXECUTION_PENDING.value:
        failures.append("coverage-state failure evidence has invalid GPU boundary")
    for field in ("error_type", "error", "traceback"):
        if not str(failure.get(field) or "").strip():
            failures.append(f"coverage-state failure evidence missing {field}")
    if manifest.get("coverage_state_schema_version") != failure.get("schema_version"):
        failures.append("root and failure-evidence schema versions differ")
    if embedded and dict(embedded) != failure:
        failures.append("embedded coverage_state differs from failure evidence")
    if resolved_artifact is not None and resolved_artifact != failure_path.resolve():
        failures.append("resolved failure artifact path mismatch")

    return {
        "applicable": True,
        "status": "PASS" if not failures else "FAIL",
        "coverage_state_status": VerificationStatus.FAILED.value,
        "gpu_runtime_status": str(manifest.get("gpu_runtime_status") or ""),
        "artifact_mode": "failure-evidence",
        "failures": failures,
    }


def _validate_success_mode(
    run_root: Path,
    manifest: Mapping[str, Any],
    embedded: Mapping[str, Any],
    resolved_artifact: Path | None,
    state: str,
    gpu_state: str,
    failures: list[str],
) -> dict[str, Any]:
    coverage_root = run_root / "coverage-state"
    failure_path = run_root / "coverage_state_failure.json"
    if state not in _NONFAILED_STATES:
        failures.append(f"nonfailed coverage state is invalid: {state}")
    if manifest.get("status") != "PASS":
        failures.append(
            "nonfailed coverage state requires root status=PASS: "
            f"{manifest.get('status')}"
        )
    if str(manifest.get("coverage_state_path")) != "coverage-state/manifest.json":
        failures.append("nonfailed coverage state must point to coverage-state/manifest.json")
    if failure_path.exists():
        failures.append("stale coverage_state_failure.json retained after successful resolution")
    if not coverage_root.is_dir():
        failures.append("coverage-state directory missing")
    else:
        _require_files(coverage_root, _COVERAGE_REQUIRED_FILES, failures, "coverage-state")
        for failure in verify_sha256s(coverage_root):
            failures.append(f"coverage-state SHA256: {failure}")

    nested_manifest = _json_object(
        coverage_root / "manifest.json",
        failures,
        "coverage-state manifest",
    )
    if nested_manifest.get("schema_version") != "all-auto-coverage-state-v1":
        failures.append("coverage-state manifest schema_version mismatch")
    if manifest.get("coverage_state_schema_version") != nested_manifest.get("schema_version"):
        failures.append("root and nested coverage schema versions differ")
    if nested_manifest.get("status") != state:
        failures.append("root and nested coverage states differ")
    if nested_manifest.get("gpu_runtime_status") != gpu_state:
        failures.append("root and nested GPU states differ")
    if embedded and dict(embedded) != nested_manifest:
        failures.append("embedded coverage_state differs from nested manifest")
    if nested_manifest.get("constructor_model_count") != 36:
        failures.append(
            "constructor model count mismatch: "
            f"expected=36, actual={nested_manifest.get('constructor_model_count')}"
        )

    constructor_rows = _json_list(
        coverage_root / "AUTO_CONSTRUCTOR_CONTRACT_MATRIX.json",
        failures,
        "constructor contract matrix",
    )
    names = [
        str(row.get("name") or "")
        for row in constructor_rows
        if isinstance(row, Mapping)
    ]
    if len(constructor_rows) != 36:
        failures.append(
            f"constructor matrix row count mismatch: expected=36, actual={len(constructor_rows)}"
        )
    if len(names) != len(constructor_rows):
        failures.append("constructor matrix contains a non-object row")
    if len(set(names)) != len(names) or any(not name for name in names):
        failures.append("constructor matrix model names are empty or duplicated")
    _validate_count_map(
        nested_manifest.get("constructor_status_counts"),
        len(constructor_rows),
        failures,
        "constructor_status_counts",
    )

    resolved_rows = _json_list(
        coverage_root / "API_ARGUMENT_COVERAGE_RESOLVED.json",
        failures,
        "resolved argument coverage",
    )
    if any(not isinstance(row, Mapping) for row in resolved_rows):
        failures.append("resolved argument coverage contains a non-object row")
    summary = _json_object(
        coverage_root / "COVERAGE_SUMMARY.json",
        failures,
        "coverage summary",
    )
    argument_count = summary.get("argument_count")
    if argument_count != len(resolved_rows):
        failures.append(
            "resolved argument count mismatch: "
            f"summary={argument_count}, rows={len(resolved_rows)}"
        )
    if summary.get("overall_status") != state:
        failures.append("coverage summary and root verification states differ")
    _validate_count_map(
        summary.get("verification_status_counts"),
        len(resolved_rows),
        failures,
        "verification_status_counts",
    )

    result_rows: int | None = None
    result_path = run_root / "API_ARGUMENT_COVERAGE_RESULT.parquet"
    if result_path.is_file():
        try:
            result_rows = len(pd.read_parquet(result_path))
        except Exception as exc:  # pragma: no cover - backend-specific message
            failures.append(
                "API coverage result parquet unreadable: "
                f"{type(exc).__name__}: {exc}"
            )
    if result_rows == 0:
        failures.append("API coverage result parquet must not be empty")
    if result_rows is not None and nested_manifest.get("api_result_count") != result_rows:
        failures.append(
            "API result count mismatch: "
            f"manifest={nested_manifest.get('api_result_count')}, rows={result_rows}"
        )

    expected_nested_path = coverage_root / "manifest.json"
    if resolved_artifact is not None and resolved_artifact != expected_nested_path.resolve():
        failures.append("resolved coverage-state artifact path mismatch")

    return {
        "applicable": True,
        "status": "PASS" if not failures else "FAIL",
        "coverage_state_status": state,
        "gpu_runtime_status": gpu_state,
        "artifact_mode": "coverage-state-bundle",
        "constructor_model_count": len(constructor_rows),
        "resolved_argument_count": len(resolved_rows),
        "api_result_count": result_rows,
        "failures": failures,
    }


def verify_coverage_state_artifacts(
    run_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the integrated API coverage and coverage-state artifact contract."""

    coverage_root = run_root / "coverage-state"
    failure_path = run_root / "coverage_state_failure.json"
    applicable = bool(
        manifest.get("coverage_state_status") is not None
        or coverage_root.exists()
        or failure_path.exists()
    )
    if not applicable:
        return {
            "applicable": False,
            "status": "NOT_APPLICABLE",
            "coverage_state_status": None,
            "gpu_runtime_status": None,
            "failures": [],
        }

    failures: list[str] = []
    _require_files(run_root, _ROOT_REQUIRED_FILES, failures, "API coverage root")
    if manifest.get("schema_version") != "all-auto-api-coverage-v1":
        failures.append("integrated API coverage manifest schema_version mismatch")

    required_fields = {
        "coverage_state_schema_version",
        "coverage_state_status",
        "verification_status",
        "coverage_state_path",
        "gpu_runtime_status",
        "coverage_state",
    }
    for field in sorted(required_fields - set(manifest)):
        failures.append(f"integrated manifest missing field: {field}")

    state = str(manifest.get("coverage_state_status") or "")
    verification_state = str(manifest.get("verification_status") or "")
    gpu_state = str(manifest.get("gpu_runtime_status") or "")
    if state not in {item.value for item in VerificationStatus}:
        failures.append(f"unknown coverage_state_status: {state}")
    if verification_state != state:
        failures.append(
            "verification_status mismatch: "
            f"coverage_state_status={state}, verification_status={verification_state}"
        )
    if gpu_state != VerificationStatus.EXECUTION_PENDING.value:
        failures.append(
            "GPU boundary must remain EXECUTION_PENDING for CPU-safe API coverage: "
            f"actual={gpu_state}"
        )

    embedded = manifest.get("coverage_state")
    if not isinstance(embedded, Mapping) or not embedded:
        failures.append("integrated manifest coverage_state must be a non-empty object")
        embedded = {}

    resolved_artifact = _safe_relative_path(
        run_root,
        manifest.get("coverage_state_path"),
        failures,
    )
    if state == VerificationStatus.FAILED.value:
        return _validate_failure_mode(
            run_root,
            manifest,
            embedded,
            resolved_artifact,
            failures,
        )
    return _validate_success_mode(
        run_root,
        manifest,
        embedded,
        resolved_artifact,
        state,
        gpu_state,
        failures,
    )


def verify_run_with_coverage(run_root: Path) -> dict[str, Any]:
    """Run legacy verification and then apply the coverage-state contract."""

    from .runner import verify_run

    base_result = verify_run(run_root)
    manifest_path = run_root / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    else:
        manifest = {}

    coverage_result = verify_coverage_state_artifacts(run_root, manifest)
    failures = list(base_result.get("failures") or [])
    failures.extend(
        f"coverage-state:{failure}"
        for failure in coverage_result.get("failures", [])
    )
    result = {
        **base_result,
        "status": (
            "PASS"
            if not failures and manifest.get("status") == "PASS"
            else "FAIL"
        ),
        "coverage_state_verification": coverage_result,
        "failures": failures,
    }
    write_json(run_root / "VERIFICATION_REPORT.json", result)
    write_sha256s(run_root)
    return result
