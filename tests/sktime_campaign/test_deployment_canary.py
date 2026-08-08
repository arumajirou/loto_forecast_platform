from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.sktime_campaign.deployment_canary import (
    CanaryActivationRequest,
    RuntimeProbeEvidence,
    activate_shadow_canary,
    bootstrap_deployment_state,
    canonical_sha256,
)

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64
HEX_F = "f" * 64


def subject(target: str) -> dict:
    return {
        "registry_target": "file+json:///tmp/registry.json",
        "model_id": "sktime-model",
        "model_revision": "abcdef1",
        "shadow_candidate_id": "theta",
        "model_artifact_sha256": HEX_A,
        "data_snapshot_sha256": HEX_B,
        "runtime_environment_sha256": HEX_C,
        "code_sha256": HEX_D,
    }


def probe(**overrides) -> dict:
    payload = {
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
    }
    payload.update(overrides)
    return payload


def request(tmp_path: Path, **overrides) -> CanaryActivationRequest:
    state_path = tmp_path / "deployment.json"
    target = f"file+json://{state_path}"
    state = bootstrap_deployment_state(state_path, target)
    payload = {
        "schema_version": "1.0",
        "operation": "activate_shadow_canary",
        "output_dir": str(tmp_path / "evidence"),
        "run_id": "p9-run",
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
            "subject": subject(target),
        },
        "runtime_probe": probe(),
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
    payload.update(overrides)
    return CanaryActivationRequest.model_validate(payload)


def test_bootstrap_and_activate(tmp_path: Path) -> None:
    req = request(tmp_path)
    result = activate_shadow_canary(req, committed_at_utc="2026-08-05T10:06:00Z")
    assert result["decision"] == "SHADOW_CANARY_ACTIVATED"
    assert result["post_state"]["canary_binding"]["subject"]["model_id"] == ("sktime-model")
    assert result["primary_binding_unchanged"] is True
    assert result["prediction_publication_allowed"] is False


def test_exact_retry_is_idempotent(tmp_path: Path) -> None:
    req = request(tmp_path)
    activate_shadow_canary(req, committed_at_utc="2026-08-05T10:06:00Z")
    result = activate_shadow_canary(req, committed_at_utc="2026-08-05T10:07:00Z")
    assert result["decision"] == "IDEMPOTENT_ALREADY_ACTIVATED"
    assert result["deployment_state_changed"] is False


def test_stale_state_rejected_without_mutation(tmp_path: Path) -> None:
    req = request(tmp_path)
    state_path = Path(req.deployment_target.removeprefix("file+json://"))
    before = state_path.read_bytes()
    bad = req.model_copy(update={"expected_deployment_state_sha256": HEX_A})
    with pytest.raises(ValueError, match="stale"):
        activate_shadow_canary(bad, committed_at_utc="2026-08-05T10:06:00Z")
    assert state_path.read_bytes() == before


def test_changed_replay_rejected(tmp_path: Path) -> None:
    req = request(tmp_path)
    activate_shadow_canary(req, committed_at_utc="2026-08-05T10:06:00Z")
    state_path = Path(req.deployment_target.removeprefix("file+json://"))
    current = json.loads(state_path.read_text())
    changed = req.model_copy(
        update={
            "activation_nonce": HEX_A,
            "expected_deployment_state_sha256": current["state_sha256"],
        }
    )
    with pytest.raises(ValueError, match="different canary"):
        activate_shadow_canary(changed, committed_at_utc="2026-08-05T10:07:00Z")


def test_old_probe_rejected(tmp_path: Path) -> None:
    req = request(tmp_path)
    with pytest.raises(ValueError, match="age window"):
        activate_shadow_canary(req, committed_at_utc="2026-08-05T12:00:00Z")


def test_shape_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        RuntimeProbeEvidence.model_validate(probe(actual_output_shape=[2, 3]))


def test_cuda_requires_gpu_evidence() -> None:
    with pytest.raises(ValueError, match="GPU PID"):
        RuntimeProbeEvidence.model_validate(probe(requested_device="cuda", actual_device="cuda"))


def test_cpu_fallback_rejected_by_default(tmp_path: Path) -> None:
    fallback = RuntimeProbeEvidence.model_validate(
        probe(
            requested_device="cuda",
            actual_device="cpu",
            cpu_fallback=True,
            fallback_reason="CUDA unavailable",
        )
    )
    req = request(tmp_path)
    payload = req.model_dump(mode="json")
    payload["runtime_probe"] = fallback.model_dump(mode="json")
    with pytest.raises(ValueError, match="forbidden"):
        CanaryActivationRequest.model_validate(payload)


def test_probe_subject_mismatch_rejected(tmp_path: Path) -> None:
    req = request(tmp_path)
    payload = req.model_dump(mode="json")
    payload["runtime_probe"]["model_revision"] = "1234567"
    with pytest.raises(ValueError, match="model_revision"):
        CanaryActivationRequest.model_validate(payload)


def test_symlink_state_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    target = f"file+json://{real}"
    bootstrap_deployment_state(real, target)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    req = request(tmp_path / "other")
    payload = req.model_dump(mode="json")
    payload["deployment_target"] = f"file+json://{link}"
    req2 = CanaryActivationRequest.model_validate(payload)
    with pytest.raises(ValueError, match="symbolic-link"):
        activate_shadow_canary(req2, committed_at_utc="2026-08-05T10:06:00Z")


def test_existing_canary_blocks_new_activation(tmp_path: Path) -> None:
    req = request(tmp_path)
    activate_shadow_canary(req, committed_at_utc="2026-08-05T10:06:00Z")
    state_path = Path(req.deployment_target.removeprefix("file+json://"))
    state = json.loads(state_path.read_text())
    changed_payload = req.model_dump(mode="json")
    changed_payload["expected_deployment_state_sha256"] = state["state_sha256"]
    changed_payload["activation_nonce"] = HEX_A
    changed_payload["p8"]["transaction_id"] = HEX_B
    changed = CanaryActivationRequest.model_validate(changed_payload)
    with pytest.raises(ValueError, match="different canary"):
        activate_shadow_canary(changed, committed_at_utc="2026-08-05T10:07:00Z")


def test_history_seal_detects_tamper(tmp_path: Path) -> None:
    req = request(tmp_path)
    result = activate_shadow_canary(req, committed_at_utc="2026-08-05T10:06:00Z")
    post = result["post_state"]
    post["history"][0]["activation_nonce"] = HEX_A
    payload = {key: value for key, value in post.items() if key != "state_sha256"}
    post["state_sha256"] = canonical_sha256(payload)
    from loto.sktime_campaign.deployment_canary import DeploymentState

    with pytest.raises(ValueError, match="record seal"):
        DeploymentState.model_validate(post)
