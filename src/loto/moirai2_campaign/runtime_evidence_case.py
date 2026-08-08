from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.moirai2_campaign.runtime_evidence_common import (
    CaseVerification,
    EXPECTED_QUANTILE_KEYS,
    EXPECTED_SAVE_LOAD_STATUS,
    RuntimeEvidenceGateError,
    _required_file,
    canonical_json_bytes,
    load_json_object,
    sha256_file,
)
from loto.moirai2_campaign.runtime_evidence_gpu import _verify_run_evidence
from loto.moirai2_campaign.runtime_evidence_prediction import (
    _artifact_identity,
    _require_equal,
    _require_true,
    validate_prediction_payload,
    validate_response_device,
)


def _request_identity(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": request.get("model_id"),
        "repo_id": request.get("repo_id"),
        "revision": request.get("revision"),
        "snapshot_path": request.get("snapshot_path"),
        "seed": request.get("seed"),
        "device": request.get("device"),
        "local_files_only": request.get("local_files_only"),
    }


def verify_case(
    *,
    campaign_dir: Path,
    case_name: str,
    runtime_lane: str,
    requested_device: str,
    campaign_id: str,
) -> CaseVerification:
    case_dir = campaign_dir / "cases" / case_name
    request_path = _required_file(campaign_dir, f"requests/{case_name}.json")
    request = load_json_object(request_path)
    _require_equal(
        request.get("run_id"),
        f"{campaign_id}.{case_name}",
        "request run_id differs",
    )
    _require_equal(request.get("device"), requested_device, "request device differs")
    _require_equal(request.get("seed"), 1, "request seed differs")
    _require_true(
        request.get("local_files_only"),
        "request local_files_only is not true",
    )
    case_result = load_json_object(_required_file(case_dir, "campaign_case_result.json"))
    _require_equal(case_result.get("case"), case_name, "case result name differs")
    _require_equal(case_result.get("status"), "PASS", "case result did not pass")
    _require_equal(
        int(case_result.get("launcher_return_code", -1)),
        0,
        "campaign launcher exit code differs",
    )
    _require_equal(
        case_result.get("launcher_timed_out"),
        False,
        "campaign launcher timed out",
    )
    _require_equal(
        case_result.get("request_sha256"),
        sha256_file(request_path),
        "case request SHA differs",
    )
    certification = load_json_object(_required_file(case_dir, "certification.json"))
    embedded = case_result.get("certification")
    if not isinstance(embedded, dict) or canonical_json_bytes(embedded) != canonical_json_bytes(
        certification
    ):
        raise RuntimeEvidenceGateError("embedded certification differs from artifact")
    _require_equal(certification.get("status"), "PASS", "certification did not pass")
    _require_equal(
        certification.get("runtime_lane"),
        runtime_lane,
        "certification runtime lane differs",
    )
    _require_equal(
        certification.get("requested_device"),
        requested_device,
        "certification requested device differs",
    )
    _require_true(
        certification.get("separate_process_reload"),
        "separate process reload evidence is missing",
    )
    _require_equal(
        certification.get("save_load_status"),
        EXPECTED_SAVE_LOAD_STATUS,
        "save/load status differs",
    )
    comparison = certification.get("prediction_comparison")
    if not isinstance(comparison, dict):
        raise RuntimeEvidenceGateError("prediction comparison is missing")
    for flag in (
        "distinct_processes",
        "exact_prediction_match",
        "artifact_identity_match",
        "model_identity_match",
        "covariate_identity_match",
    ):
        _require_true(comparison.get(flag), f"prediction comparison {flag} is false")
    response_a = load_json_object(_required_file(case_dir, "run-a/response.json"))
    response_b = load_json_object(_required_file(case_dir, "run-b/response.json"))
    prediction_a = validate_prediction_payload(response_a)
    prediction_b = validate_prediction_payload(response_b)
    _require_equal(prediction_a, prediction_b, "reloaded predictions differ")
    _require_equal(
        comparison.get("prediction_sha256_a"),
        prediction_a,
        "comparison prediction SHA A differs",
    )
    _require_equal(
        comparison.get("prediction_sha256_b"),
        prediction_b,
        "comparison prediction SHA B differs",
    )
    process_a = validate_response_device(
        response_a,
        runtime_lane=runtime_lane,
        requested_device=requested_device,
    )
    process_b = validate_response_device(
        response_b,
        runtime_lane=runtime_lane,
        requested_device=requested_device,
    )
    if process_a == process_b:
        raise RuntimeEvidenceGateError("provider process IDs are not distinct")
    _require_equal(comparison.get("process_a"), process_a, "comparison PID A differs")
    _require_equal(comparison.get("process_b"), process_b, "comparison PID B differs")
    evidence_a = _verify_run_evidence(
        run_dir=case_dir / "run-a",
        response=response_a,
        process_id=process_a,
        requested_device=requested_device,
    )
    evidence_b = _verify_run_evidence(
        run_dir=case_dir / "run-b",
        response=response_b,
        process_id=process_b,
        requested_device=requested_device,
    )
    for key, label, external in (
        ("run_a", "run-a", evidence_a),
        ("run_b", "run-b", evidence_b),
    ):
        retained = certification.get(key)
        if not isinstance(retained, dict):
            raise RuntimeEvidenceGateError(f"certification {key} evidence is missing")
        _require_equal(
            retained.get("process_id"),
            process_a if key == "run_a" else process_b,
            f"certification {key} process ID differs",
        )
        _require_equal(
            retained.get("external_gpu"),
            external.get("external_gpu"),
            f"certification {key} external GPU evidence differs",
        )
        _require_equal(retained.get("label"), label, f"certification {key} label differs")
        expected_retained = {
            retained_key: retained_value
            for retained_key, retained_value in external.items()
            if retained_key != "response"
        }
        _require_equal(
            retained,
            expected_retained,
            f"certification {key} evidence differs from run artifact",
        )
    artifact_a = _artifact_identity(response_a)
    artifact_b = _artifact_identity(response_b)
    _require_equal(artifact_a, artifact_b, "reload artifact identity differs")
    _require_equal(
        response_a.get("model_identity"),
        response_b.get("model_identity"),
        "reload model identity differs",
    )
    _require_equal(
        response_a.get("covariate_evidence"),
        response_b.get("covariate_evidence"),
        "reload covariate evidence differs",
    )
    _require_equal(
        request.get("revision"),
        artifact_a[0],
        "request and response model revision differ",
    )
    return CaseVerification(
        case_name=case_name,
        runtime_lane=runtime_lane,
        requested_device=requested_device,
        process_a=process_a,
        process_b=process_b,
        prediction_sha256=prediction_a,
        model_revision=artifact_a[0],
        config_sha256=artifact_a[1],
        weight_sha256=artifact_a[2],
        quantile_keys=EXPECTED_QUANTILE_KEYS,
        external_gpu_verified=requested_device == "cuda",
    )
