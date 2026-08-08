from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from loto.sktime_campaign.matrix import MODEL_SPECS
from loto.sktime_campaign.protocol import SmokeModelId
from loto.sktime_campaign.verification import (
    VerificationError,
    _is_recursive_evidence,
    _load_json,
    _safe_relative_path,
    _sha256,
    _write_json,
    _write_recursive_sha256sums,
    verify_inventory_bundle,
    verify_manifest,
    verify_sha256sums,
)


FORMAL_P1_MODEL_IDS: tuple[str, ...] = (
    SmokeModelId.NAIVE_LAST.value,
    SmokeModelId.POLYNOMIAL_TREND_D1.value,
    SmokeModelId.EXPONENTIAL_SMOOTHING.value,
    SmokeModelId.THETA.value,
)
FORMAL_P1_FORECAST_HORIZON: tuple[int, ...] = (1, 2)
FORMAL_P1_SERIES: tuple[float, ...] = (
    4,
    7,
    3,
    8,
    6,
    9,
    5,
    10,
    7,
    11,
    8,
    12,
    9,
    13,
    10,
    14,
    11,
    15,
    12,
    16,
    13,
    17,
    14,
    18,
)
FORMAL_P1_SEED = 1
FORMAL_THREAD_LIMITS: dict[str, str] = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_pass_matrix_response(directory: Path) -> dict[str, Any]:
    response = _load_json(directory / "response.json")
    if not isinstance(response, dict):
        raise VerificationError("matrix response.json must contain an object")
    if response.get("status") != "PASS":
        raise VerificationError("smoke_matrix response status is not PASS")
    if response.get("operation") != "smoke_matrix":
        raise VerificationError("matrix response operation is not smoke_matrix")
    if response.get("environment_lane") != "classic-py312":
        raise VerificationError("matrix response lane is not classic-py312")
    expected_version = response.get("expected_sktime_version")
    actual_version = response.get("actual_sktime_version")
    if expected_version != "1.0.1" or actual_version != expected_version:
        raise VerificationError(
            "matrix sktime version evidence mismatch: "
            f"expected={expected_version}, actual={actual_version}"
        )
    return response


def _verify_formal_request(run_dir: Path) -> dict[str, Any]:
    request = _load_json(run_dir / "smoke-matrix-request.json")
    if not isinstance(request, dict):
        raise VerificationError("formal P1 request must contain an object")

    expected_fields: dict[str, Any] = {
        "schema_version": "1.0",
        "operation": "smoke_matrix",
        "environment_lane": "classic-py312",
        "expected_sktime_version": "1.0.1",
        "model_ids": list(FORMAL_P1_MODEL_IDS),
        "forecast_horizon": list(FORMAL_P1_FORECAST_HORIZON),
        "series": list(FORMAL_P1_SERIES),
        "save_load": True,
        "device": "cpu",
        "seed": FORMAL_P1_SEED,
    }
    for key, expected in expected_fields.items():
        if request.get(key) != expected:
            raise VerificationError(
                f"formal P1 request mismatch for {key}: expected={expected}, got={request.get(key)}"
            )

    expected_output = (run_dir / "smoke-matrix").resolve()
    actual_output = Path(str(request.get("output_dir", ""))).resolve()
    if actual_output != expected_output:
        raise VerificationError(
            f"formal P1 output_dir mismatch: expected={expected_output}, got={actual_output}"
        )
    return request


def _verify_pass_result(
    directory: Path,
    result: dict[str, Any],
    *,
    expected_model_id: str,
) -> None:
    model_id = str(result.get("model_id", ""))
    if model_id != expected_model_id:
        raise VerificationError(
            f"matrix model ID mismatch: expected={expected_model_id}, got={model_id}"
        )

    spec = MODEL_SPECS[SmokeModelId(model_id)]
    expected_spec = {
        "class_path": spec.class_path,
        "constructor": spec.constructor,
        "required_distributions": list(spec.required_distributions),
    }
    for key, expected in expected_spec.items():
        if result.get(key) != expected:
            raise VerificationError(
                f"matrix fixed spec mismatch for {model_id}: "
                f"{key} expected={expected}, got={result.get(key)}"
            )

    if result.get("status") != "PASS":
        raise VerificationError(f"matrix model is not PASS: {model_id}")
    if result.get("device") != "cpu" or result.get("cpu_fallback") is not False:
        raise VerificationError(f"matrix CPU boundary is invalid: {model_id}")
    if result.get("seed") != FORMAL_P1_SEED:
        raise VerificationError(f"matrix seed mismatch: {model_id}")
    if result.get("input_rows") != len(FORMAL_P1_SERIES):
        raise VerificationError(f"matrix input row count mismatch: {model_id}")

    missing_dependencies = result.get("missing_dependencies")
    if missing_dependencies != []:
        raise VerificationError(f"matrix dependencies are missing: {model_id}")
    versions = result.get("dependency_versions")
    if not isinstance(versions, dict) or versions.get("sktime") != "1.0.1":
        raise VerificationError(f"matrix sktime dependency evidence is invalid: {model_id}")
    for distribution in spec.required_distributions:
        if not isinstance(versions.get(distribution), str) or not versions[distribution]:
            raise VerificationError(
                f"matrix dependency version is missing for {model_id}: {distribution}"
            )

    for phase in (
        "dependency_status",
        "import_status",
        "construct_status",
        "fit_status",
        "predict_status",
        "save_load_status",
    ):
        if result.get(phase) != "PASS":
            raise VerificationError(
                f"matrix phase is not PASS for {model_id}: {phase}={result.get(phase)}"
            )

    if result.get("prediction_finite") is not True:
        raise VerificationError(f"matrix prediction is not finite: {model_id}")

    before = result.get("prediction_before_save")
    after = result.get("prediction_after_load")
    if not isinstance(before, list) or not before:
        raise VerificationError(f"matrix prediction is missing: {model_id}")
    if before != after:
        raise VerificationError(f"matrix save/load prediction changed: {model_id}")
    if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in before):
        raise VerificationError(f"matrix prediction contains non-finite values: {model_id}")
    if result.get("prediction_shape") != [len(before)]:
        raise VerificationError(f"matrix prediction shape mismatch: {model_id}")

    horizon = result.get("forecast_horizon")
    expected_index = result.get("expected_prediction_index")
    if horizon != list(FORMAL_P1_FORECAST_HORIZON):
        raise VerificationError(f"matrix forecast horizon mismatch: {model_id}")
    if not isinstance(expected_index, list) or len(expected_index) != len(before):
        raise VerificationError(f"matrix prediction index evidence mismatch: {model_id}")

    save_load = result.get("save_load")
    if not isinstance(save_load, dict) or save_load.get("status") != "PASS":
        raise VerificationError(f"matrix save/load status is not PASS: {model_id}")
    if save_load.get("exact_prediction_match") is not True:
        raise VerificationError(f"matrix exact prediction match is not true: {model_id}")
    archive_name = str(save_load.get("artifact", ""))
    archive = _safe_relative_path(directory, archive_name)
    if not archive.is_file() or archive.stat().st_size <= 0:
        raise VerificationError(f"matrix model archive is missing or empty: {model_id}")
    if save_load.get("artifact_sha256") != _sha256(archive):
        raise VerificationError(f"matrix model archive SHA-256 mismatch: {model_id}")


def verify_matrix_bundle(directory: Path) -> dict[str, Any]:
    """Verify all formal P1 models and reject partial aggregate success."""

    response = _require_pass_matrix_response(directory)
    matrix = _load_json(directory / "SMOKE_MATRIX.json")
    if not isinstance(matrix, dict):
        raise VerificationError("SMOKE_MATRIX.json must contain an object")
    if matrix.get("status") != "PASS":
        raise VerificationError("smoke matrix aggregate status is not PASS")
    if matrix.get("device") != "cpu" or matrix.get("cpu_fallback") is not False:
        raise VerificationError("smoke matrix CPU boundary is invalid")
    if matrix.get("seed") != FORMAL_P1_SEED:
        raise VerificationError("smoke matrix seed is not the formal seed")
    if matrix.get("thread_limits") != FORMAL_THREAD_LIMITS:
        raise VerificationError(
            "smoke matrix thread limits mismatch: "
            f"expected={FORMAL_THREAD_LIMITS}, got={matrix.get('thread_limits')}"
        )

    expected_input_contract = {
        "series_rows": len(FORMAL_P1_SERIES),
        "series_sha256": _canonical_sha256(list(FORMAL_P1_SERIES)),
        "forecast_horizon": list(FORMAL_P1_FORECAST_HORIZON),
        "forecast_horizon_sha256": _canonical_sha256(list(FORMAL_P1_FORECAST_HORIZON)),
    }
    if matrix.get("input_contract") != expected_input_contract:
        raise VerificationError(
            "formal P1 input contract mismatch: "
            f"expected={expected_input_contract}, got={matrix.get('input_contract')}"
        )

    requested = matrix.get("requested_model_ids")
    if requested != list(FORMAL_P1_MODEL_IDS):
        raise VerificationError(
            f"formal P1 model IDs mismatch: expected={list(FORMAL_P1_MODEL_IDS)}, got={requested}"
        )

    results = matrix.get("results")
    if not isinstance(results, list) or len(results) != len(FORMAL_P1_MODEL_IDS):
        raise VerificationError("formal P1 result count mismatch")
    if not all(isinstance(result, dict) for result in results):
        raise VerificationError("formal P1 matrix contains a non-object result")

    result_ids = [str(result.get("model_id", "")) for result in results]
    if result_ids != list(FORMAL_P1_MODEL_IDS):
        raise VerificationError(
            "formal P1 result order or IDs mismatch: "
            f"expected={list(FORMAL_P1_MODEL_IDS)}, got={result_ids}"
        )

    for expected_model_id, result in zip(FORMAL_P1_MODEL_IDS, results, strict=True):
        _verify_pass_result(
            directory,
            result,
            expected_model_id=expected_model_id,
        )

    summary = matrix.get("summary")
    if not isinstance(summary, dict):
        raise VerificationError("formal P1 matrix summary is missing")
    expected_counts = {
        "PASS": len(FORMAL_P1_MODEL_IDS),
        "PARTIAL": 0,
        "FAILED": 0,
        "UNAVAILABLE": 0,
    }
    if summary.get("status") != "PASS":
        raise VerificationError("formal P1 summary status is not PASS")
    if summary.get("total") != len(FORMAL_P1_MODEL_IDS):
        raise VerificationError("formal P1 summary total mismatch")
    if summary.get("counts") != expected_counts:
        raise VerificationError(
            "formal P1 summary counts mismatch: "
            f"expected={expected_counts}, got={summary.get('counts')}"
        )
    if summary.get("all_requested_models_passed") is not True:
        raise VerificationError("formal P1 all-model pass flag is not true")

    if response.get("matrix") != matrix:
        raise VerificationError("matrix response evidence differs from persisted SMOKE_MATRIX.json")

    verify_manifest(directory)
    sha_records = verify_sha256sums(directory)
    return {
        "status": "PASS",
        "operation": "smoke_matrix",
        "model_ids": list(FORMAL_P1_MODEL_IDS),
        "passed": len(FORMAL_P1_MODEL_IDS),
        "input_contract": expected_input_contract,
        "thread_limits": FORMAL_THREAD_LIMITS,
        "sha256_records": len(sha_records),
    }


def finalize_p1_run(run_dir: Path) -> dict[str, Any]:
    """Verify inventory plus the four-model classic P1 smoke matrix."""

    run_dir = run_dir.resolve()
    request = _verify_formal_request(run_dir)
    inventory = verify_inventory_bundle(run_dir / "inventory")
    matrix = verify_matrix_bundle(run_dir / "smoke-matrix")
    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "certification_scope": "sktime-classic-py312-p1",
        "sktime_version": "1.0.1",
        "formal_request_sha256": _canonical_sha256(request),
        "inventory": inventory,
        "smoke_matrix": matrix,
        "certification_boundaries": {
            "dynamic_inventory": "VERIFIED",
            "four_model_fit_predict_save_load": "VERIFIED",
            "all_forecaster_runtime": "EXECUTION_PENDING",
            "optional_dependency_families": "EXECUTION_PENDING",
            "chronological_evaluation": "EXECUTION_PENDING",
            "shared_worker_integration": "NOT_APPLICABLE",
            "gpu_runtime": "NOT_APPLICABLE",
            "accuracy_improvement": "NOT_CLAIMED",
        },
    }

    preexisting_files = sorted(
        path
        for path in run_dir.rglob("*")
        if _is_recursive_evidence(run_dir, path)
        and path.relative_to(run_dir).as_posix()
        not in {"ARTIFACT_MANIFEST.json", "VERIFICATION_REPORT.json"}
    )
    report["top_level_sha256_records"] = len(preexisting_files) + 2
    _write_json(run_dir / "VERIFICATION_REPORT.json", report)

    manifest_files = sorted(
        path
        for path in run_dir.rglob("*")
        if _is_recursive_evidence(run_dir, path)
        and path.relative_to(run_dir).as_posix() != "ARTIFACT_MANIFEST.json"
    )
    manifest = {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "sktime-classic-py312-p1",
        "excluded_volatile": ["**/*.log", "logs/**", "exit_code.txt"],
        "files": [
            {
                "path": path.relative_to(run_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in manifest_files
        ],
    }
    _write_json(run_dir / "ARTIFACT_MANIFEST.json", manifest)
    _write_recursive_sha256sums(run_dir)
    top_level_records = verify_sha256sums(run_dir, recursive=True)
    if len(top_level_records) != report["top_level_sha256_records"]:
        raise VerificationError("top-level P1 SHA256SUMS record count mismatch")
    return report
