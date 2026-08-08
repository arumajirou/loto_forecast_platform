from __future__ import annotations

from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .persistence_contract import (
    PersistenceEvidence,
    PersistenceSpec,
    canonical_sha256,
    manifest_sha256,
)
from .torch_models import TorchDeviceContract, certify_device_use


class PersistenceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    passed: bool
    failure_class: str | None = None
    message: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class PersistenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["PERSISTENCE_CERTIFIED", "FAILED"]
    task_id: str
    checks: tuple[PersistenceCheck, ...]
    artifact_manifest_sha256: str
    evidence_sha256: str


def _check(
    name: str,
    passed: bool,
    failure_class: str,
    message: str,
    **evidence: Any,
) -> PersistenceCheck:
    return PersistenceCheck(
        name=name,
        passed=passed,
        failure_class=None if passed else failure_class,
        message=None if passed else message,
        evidence=evidence,
    )


def _device_contract(accelerator: str, device_index: int | None) -> TorchDeviceContract:
    if accelerator == "cpu":
        return TorchDeviceContract(
            requested_accelerator="cpu",
            devices=(),
            allow_cpu_fallback=False,
            require_gpu_pid=False,
            require_vram_evidence=False,
        )
    return TorchDeviceContract(
        requested_accelerator="gpu",
        devices=(0 if device_index is None else device_index,),
        allow_cpu_fallback=False,
        require_gpu_pid=True,
        require_vram_evidence=True,
    )


def certify_persistence(spec: PersistenceSpec, evidence: PersistenceEvidence) -> PersistenceReport:
    checks: list[PersistenceCheck] = []
    task = evidence.task
    identity_ok = (
        task.model_id == spec.model_id
        and task.family == spec.family
        and task.public_name == spec.public_name
        and task.method in spec.methods
        and evidence.before_snapshot.model_id == spec.model_id
        and evidence.after_snapshot.model_id == spec.model_id
        and evidence.before_snapshot.family == spec.family
        and evidence.after_snapshot.family == spec.family
        and evidence.before_snapshot.public_name == spec.public_name
        and evidence.after_snapshot.public_name == spec.public_name
        and evidence.before_snapshot.class_path == evidence.after_snapshot.class_path
        and evidence.before_snapshot.parameters_sha256 == evidence.after_snapshot.parameters_sha256
    )
    checks.append(
        _check(
            "model_identity",
            identity_ok,
            "MODEL_IDENTITY_MISMATCH",
            "loaded model identity differs from the saved model",
        )
    )

    process_ok = (
        evidence.save_process_ended
        and evidence.loaded_from_disk
        and not evidence.object_identity_reused
        and evidence.save_process_pid != evidence.load_process_pid
    )
    checks.append(
        _check(
            "process_boundary",
            process_ok,
            "PROCESS_BOUNDARY_MISSING",
            "save/load must cross a terminated process boundary and reload from disk",
            save_pid=evidence.save_process_pid,
            load_pid=evidence.load_process_pid,
        )
    )

    artifact_ok = bool(evidence.artifacts) and all(
        artifact.size_bytes_at_save == artifact.size_bytes_at_load
        and artifact.sha256_at_save == artifact.sha256_at_load
        for artifact in evidence.artifacts
    )
    checks.append(
        _check(
            "artifact_integrity",
            artifact_ok,
            "ARTIFACT_INTEGRITY_MISMATCH",
            "saved artifacts changed before loading",
            artifact_count=len(evidence.artifacts),
        )
    )

    before = evidence.prediction_before.array()
    after = evidence.prediction_after.array()
    prediction_ok = before.shape == after.shape and np.allclose(
        before,
        after,
        atol=spec.prediction_atol,
        rtol=spec.prediction_rtol,
    )
    checks.append(
        _check(
            "prediction_replay",
            prediction_ok,
            "PREDICTION_REPLAY_MISMATCH",
            "prediction changed after save/process-exit/load",
            before_shape=evidence.prediction_before.shape,
            after_shape=evidence.prediction_after.shape,
            max_abs_delta=(
                None if before.shape != after.shape else float(np.max(np.abs(before - after)))
            ),
        )
    )

    fitted_ok = evidence.before_snapshot.fitted and evidence.after_snapshot.fitted
    checks.append(
        _check(
            "fitted_state",
            fitted_ok,
            "FITTED_STATE_MISSING",
            "loaded model is not ready for prediction",
        )
    )

    method = task.method
    clean_ok = True
    if method == "manual_clean":
        clean_ok = (
            evidence.clean_requested
            and spec.supports_clean
            and not evidence.after_snapshot.training_state_present
            and not evidence.after_snapshot.covariate_state_present
        )
    elif evidence.clean_requested:
        clean_ok = False
    checks.append(
        _check(
            "clean_save",
            clean_ok,
            "CLEAN_SAVE_CONTRACT_FAILED",
            "clean save did not remove retained global training state",
        )
    )

    torch_companion_ok = True
    if spec.torch_backed and method in {
        "manual",
        "manual_clean",
        "weights",
        "cross_device_cpu",
        "cross_device_cuda",
    }:
        torch_companion_ok = any(artifact.path.endswith(".ckpt") for artifact in evidence.artifacts)
    checks.append(
        _check(
            "torch_weight_artifact",
            torch_companion_ok,
            "TORCH_WEIGHT_ARTIFACT_MISSING",
            "torch manual persistence requires a companion .ckpt weight artifact",
        )
    )

    checkpoint_ok = True
    if method in {"checkpoint_best", "checkpoint_last"}:
        expected_kind = "best" if method.endswith("best") else "last"
        checkpoint_ok = (
            spec.supports_checkpoint
            and evidence.checkpoint_kind == expected_kind
            and evidence.trainer_state_restored is True
            and evidence.optimizer_state_restored is True
            and evidence.scheduler_state_restored is True
            and any(expected_kind in artifact.path for artifact in evidence.artifacts)
        )
    checks.append(
        _check(
            "checkpoint_restore",
            checkpoint_ok,
            "CHECKPOINT_RESTORE_INCOMPLETE",
            "checkpoint load did not restore the selected training state",
        )
    )

    weights_ok = True
    if method == "weights":
        weights_ok = (
            spec.supports_weights
            and evidence.model_initialized_before_weights is True
            and evidence.weights_loaded is True
            and evidence.encoders_loaded is True
        )
    checks.append(
        _check(
            "weights_restore",
            weights_ok,
            "WEIGHTS_RESTORE_INCOMPLETE",
            "load_weights did not restore weights and encoders into a new model",
        )
    )

    map_location_ok = True
    if method == "cross_device_cpu":
        map_location_ok = (evidence.requested_map_location or "").lower() == "cpu"
    elif method == "cross_device_cuda":
        map_location_ok = (evidence.requested_map_location or "").lower().startswith("cuda")
    checks.append(
        _check(
            "map_location",
            map_location_ok,
            "MAP_LOCATION_MISMATCH",
            "cross-device load did not use the requested map_location",
        )
    )

    device_ok = True
    device_evidence: dict[str, Any] = {"status": "GPU_NOT_APPLICABLE"}
    if spec.torch_backed:
        if evidence.device_before is None or evidence.device_after is None:
            device_ok = False
            device_evidence = {"failure_class": "DEVICE_EVIDENCE_MISSING"}
        else:
            before_contract = _device_contract(
                evidence.device_before.requested_accelerator,
                evidence.device_before.device_index,
            )
            before_report = certify_device_use(before_contract, evidence.device_before)
            target = spec.requested_accelerator
            if method == "cross_device_cpu":
                target = "cpu"
            elif method == "cross_device_cuda":
                target = "gpu"
            after_contract = _device_contract(target, spec.device_index)
            after_report = certify_device_use(after_contract, evidence.device_after)
            device_ok = before_report["passed"] and after_report["passed"]
            device_evidence = {"before": before_report, "after": after_report}
    checks.append(
        _check(
            "device_certification",
            device_ok,
            "DEVICE_CERTIFICATION_FAILED",
            "loaded model device evidence is incomplete or indicates CPU fallback",
            **device_evidence,
        )
    )

    passed = all(check.passed for check in checks)
    evidence_payload = evidence.model_dump(mode="json")
    return PersistenceReport(
        status="PERSISTENCE_CERTIFIED" if passed else "FAILED",
        task_id=f"{task.model_id}:{task.method}",
        checks=tuple(checks),
        artifact_manifest_sha256=manifest_sha256(evidence.artifacts),
        evidence_sha256=canonical_sha256(evidence_payload),
    )
