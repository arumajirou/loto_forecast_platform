from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.sktime_campaign.deployment_artifacts import (
    P9VerificationError,
    persist_p9,
    verify_p9,
)
from loto.sktime_campaign.deployment_canary import (
    CanaryActivationRequest,
    bootstrap_deployment_state,
)

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64
HEX_F = "f" * 64


def request(tmp_path: Path) -> CanaryActivationRequest:
    state_path = tmp_path / "deployment.json"
    target = f"file+json://{state_path}"
    state = bootstrap_deployment_state(state_path, target)
    payload = {
        "schema_version": "1.0",
        "operation": "activate_shadow_canary",
        "output_dir": str(tmp_path / "evidence"),
        "run_id": "p9-artifacts",
        "git_commit": "abcdef1",
        "code_sha256": HEX_D,
        "config_sha256": HEX_E,
        "requested_at_utc": "2026-08-05T10:05:00Z",
        "deployment_target": target,
        "expected_deployment_state_sha256": state.state_sha256,
        "activation_nonce": HEX_F,
        "p8": {
            "schema_version": "1.0",
            "p8_bundle_sha256": HEX_A,
            "p8_receipt_sha256": HEX_B,
            "p8_post_state_sha256": HEX_C,
            "registry_state_sha256": HEX_D,
            "transaction_id": HEX_E,
            "decision": "REGISTRY_TRANSACTION_COMMITTED",
            "promotion_status": "REGISTERED_NOT_DEPLOYED",
            "deployment_status": "NOT_DEPLOYED",
            "subject": {
                "registry_target": "file+json:///tmp/registry.json",
                "model_id": "sktime-model",
                "model_revision": "abcdef1",
                "shadow_candidate_id": "theta",
                "model_artifact_sha256": HEX_A,
                "data_snapshot_sha256": HEX_B,
                "runtime_environment_sha256": HEX_C,
                "code_sha256": HEX_D,
            },
        },
        "runtime_probe": {
            "schema_version": "1.0",
            "probe_run_id": "probe-1",
            "probed_at_utc": "2026-08-05T10:00:00Z",
            "model_id": "sktime-model",
            "model_revision": "abcdef1",
            "model_artifact_sha256": HEX_A,
            "runtime_environment_sha256": HEX_C,
            "code_sha256": HEX_D,
            "input_sha256": HEX_E,
            "prediction_sha256": HEX_F,
            "load_success": True,
            "input_validation_success": True,
            "inference_success": True,
            "save_load_reprediction_match": True,
            "finite_output": True,
            "expected_output_shape": [1, 3],
            "actual_output_shape": [1, 3],
            "requested_device": "cpu",
            "actual_device": "cpu",
            "process_id": 100,
            "gpu_process_id": None,
            "gpu_vram_mb": None,
            "cpu_fallback": False,
            "fallback_reason": None,
        },
        "policy": {
            "minimum_shadow_draws": 3,
            "maximum_probe_age_seconds": 3600,
            "allow_cpu_fallback": False,
            "require_primary_unchanged": True,
            "prediction_publication_allowed": False,
            "automatic_primary_promotion": False,
            "automatic_retraining": False,
            "automatic_rollback": False,
        },
    }
    return CanaryActivationRequest.model_validate(payload)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def test_persist_and_verify(tmp_path: Path) -> None:
    req = request(tmp_path)
    response = persist_p9(req, committed_at_utc="2026-08-05T10:06:00Z")
    assert response["decision"] == "SHADOW_CANARY_ACTIVATED"
    result = verify_p9(Path(req.output_dir), req)
    assert result["status"] == "PASS"


@pytest.mark.parametrize(
    "filename",
    [
        "P8_LINEAGE.json",
        "RUNTIME_PROBE.json",
        "ACTIVATION_RECEIPT.json",
        "POST_DEPLOYMENT_STATE.json",
        "response.json",
    ],
)
def test_tamper_is_rejected(tmp_path: Path, filename: str) -> None:
    req = request(tmp_path)
    persist_p9(req, committed_at_utc="2026-08-05T10:06:00Z")
    path = Path(req.output_dir) / filename
    payload = json.loads(path.read_text())
    payload["tampered"] = True
    write_json(path, payload)
    with pytest.raises(P9VerificationError):
        verify_p9(Path(req.output_dir), req)


def test_manifest_tamper_rejected(tmp_path: Path) -> None:
    req = request(tmp_path)
    persist_p9(req, committed_at_utc="2026-08-05T10:06:00Z")
    path = Path(req.output_dir) / "ARTIFACT_MANIFEST.json"
    payload = json.loads(path.read_text())
    payload["scope"] = "changed"
    write_json(path, payload)
    with pytest.raises(P9VerificationError, match="scope"):
        verify_p9(Path(req.output_dir), req)


def test_sha_coverage_rejected(tmp_path: Path) -> None:
    req = request(tmp_path)
    persist_p9(req, committed_at_utc="2026-08-05T10:06:00Z")
    path = Path(req.output_dir) / "SHA256SUMS"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(P9VerificationError):
        verify_p9(Path(req.output_dir), req)
