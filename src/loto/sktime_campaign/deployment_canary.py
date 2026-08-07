from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _parse_utc(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{label} must use strict UTC Z format") from exc


class RegisteredSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_target: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    shadow_candidate_id: str = Field(min_length=1)
    model_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class P8RegistrationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    p8_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p8_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p8_post_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registry_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["REGISTRY_TRANSACTION_COMMITTED"]
    promotion_status: Literal["REGISTERED_NOT_DEPLOYED"]
    deployment_status: Literal["NOT_DEPLOYED"]
    subject: RegisteredSubject


class RuntimeProbeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    probe_run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    probed_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    model_id: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    model_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    load_success: Literal[True] = True
    input_validation_success: Literal[True] = True
    inference_success: Literal[True] = True
    save_load_reprediction_match: Literal[True] = True
    finite_output: Literal[True] = True
    expected_output_shape: list[int] = Field(min_length=1)
    actual_output_shape: list[int] = Field(min_length=1)
    requested_device: Literal["cpu", "cuda"]
    actual_device: Literal["cpu", "cuda"]
    process_id: int = Field(gt=0)
    gpu_process_id: int | None = Field(default=None, gt=0)
    gpu_vram_mb: float | None = Field(default=None, gt=0.0)
    cpu_fallback: bool = False
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def validate_probe(self) -> "RuntimeProbeEvidence":
        _parse_utc(self.probed_at_utc, label="probed_at_utc")
        if self.expected_output_shape != self.actual_output_shape:
            raise ValueError("runtime probe output shape mismatch")
        if any(item <= 0 for item in self.actual_output_shape):
            raise ValueError("runtime probe output dimensions must be positive")
        if self.actual_device == "cuda":
            if self.gpu_process_id is None or self.gpu_vram_mb is None:
                raise ValueError("CUDA probe requires GPU PID and VRAM evidence")
            if self.cpu_fallback:
                raise ValueError("CUDA probe cannot claim CPU fallback")
        if self.cpu_fallback:
            if not (
                self.requested_device == "cuda" and self.actual_device == "cpu"
            ):
                raise ValueError("CPU fallback device transition is invalid")
            if not self.fallback_reason:
                raise ValueError("CPU fallback requires a reason")
        elif self.requested_device != self.actual_device:
            raise ValueError("runtime device drift without explicit fallback")
        return self


class CanaryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_shadow_draws: int = Field(default=3, ge=1)
    maximum_probe_age_seconds: int = Field(default=3600, ge=60, le=86400)
    allow_cpu_fallback: bool = False
    require_primary_unchanged: Literal[True] = True
    prediction_publication_allowed: Literal[False] = False
    automatic_primary_promotion: Literal[False] = False
    automatic_retraining: Literal[False] = False
    automatic_rollback: Literal[False] = False


class DeploymentBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: RegisteredSubject
    activated_at_utc: str
    activation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_p8_transaction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["primary", "shadow_canary"]


class DeploymentHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    generation: int = Field(ge=1)
    activation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_at_utc: str
    previous_primary: DeploymentBinding | None
    previous_canary: DeploymentBinding | None
    new_canary: DeploymentBinding
    pre_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_record(self) -> "DeploymentHistoryRecord":
        _parse_utc(self.committed_at_utc, label="committed_at_utc")
        payload = self.model_dump(mode="json", exclude={"record_sha256"})
        if canonical_sha256(payload) != self.record_sha256:
            raise ValueError("deployment history record seal mismatch")
        return self


class DeploymentState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    backend: Literal["file-json-deployment-cas-v1"]
    deployment_target: str = Field(min_length=1)
    generation: int = Field(ge=0)
    primary_binding: DeploymentBinding | None = None
    canary_binding: DeploymentBinding | None = None
    consumed_activation_ids: list[str] = Field(default_factory=list)
    consumed_activation_nonces: list[str] = Field(default_factory=list)
    history: list[DeploymentHistoryRecord] = Field(default_factory=list)
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_state(self) -> "DeploymentState":
        if len(self.consumed_activation_ids) != len(
            set(self.consumed_activation_ids)
        ):
            raise ValueError("consumed activation IDs must be unique")
        if len(self.consumed_activation_nonces) != len(
            set(self.consumed_activation_nonces)
        ):
            raise ValueError("consumed activation nonces must be unique")
        if self.generation != len(self.history):
            raise ValueError("deployment generation/history length mismatch")
        if len(self.consumed_activation_ids) != self.generation:
            raise ValueError("activation ID ledger length mismatch")
        if len(self.consumed_activation_nonces) != self.generation:
            raise ValueError("activation nonce ledger length mismatch")
        payload = self.model_dump(mode="json", exclude={"state_sha256"})
        if canonical_sha256(payload) != self.state_sha256:
            raise ValueError("deployment state seal mismatch")
        for index, record in enumerate(self.history, start=1):
            if record.generation != index:
                raise ValueError("deployment history generation mismatch")
        return self


class CanaryActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["activate_shadow_canary"] = "activate_shadow_canary"
    output_dir: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_at_utc: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    )
    deployment_target: str = Field(min_length=1)
    expected_deployment_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    p8: P8RegistrationEvidence
    runtime_probe: RuntimeProbeEvidence
    policy: CanaryPolicy = Field(default_factory=CanaryPolicy)

    @model_validator(mode="after")
    def validate_request(self) -> "CanaryActivationRequest":
        _parse_utc(self.requested_at_utc, label="requested_at_utc")
        subject = self.p8.subject
        probe = self.runtime_probe
        exact_pairs = {
            "model_id": (subject.model_id, probe.model_id),
            "model_revision": (subject.model_revision, probe.model_revision),
            "model_artifact_sha256": (
                subject.model_artifact_sha256,
                probe.model_artifact_sha256,
            ),
            "runtime_environment_sha256": (
                subject.runtime_environment_sha256,
                probe.runtime_environment_sha256,
            ),
            "code_sha256": (subject.code_sha256, probe.code_sha256),
        }
        for label, (expected, observed) in exact_pairs.items():
            if expected != observed:
                raise ValueError(f"runtime probe changed registered {label}")
        if probe.cpu_fallback and not self.policy.allow_cpu_fallback:
            raise ValueError("CPU fallback is forbidden by canary policy")
        return self


def _sealed_state(payload: dict[str, Any]) -> DeploymentState:
    return DeploymentState.model_validate(
        {**payload, "state_sha256": canonical_sha256(payload)}
    )


def empty_deployment_state(deployment_target: str) -> DeploymentState:
    payload = {
        "schema_version": "1.0",
        "backend": "file-json-deployment-cas-v1",
        "deployment_target": deployment_target,
        "generation": 0,
        "primary_binding": None,
        "canary_binding": None,
        "consumed_activation_ids": [],
        "consumed_activation_nonces": [],
        "history": [],
    }
    return _sealed_state(payload)


def _state_path_from_target(target: str) -> Path:
    prefix = "file+json://"
    if not target.startswith(prefix):
        raise ValueError("deployment target must use file+json://")
    raw = target[len(prefix) :]
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError("deployment state path must be absolute")
    return path


def _load_state(path: Path) -> DeploymentState:
    if path.is_symlink():
        raise ValueError("symbolic-link deployment state is forbidden")
    try:
        return DeploymentState.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"unable to read deployment state: {exc}") from exc


def _atomic_write_state(path: Path, state: DeploymentState) -> None:
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(state.model_dump_json(indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def bootstrap_deployment_state(path: Path, deployment_target: str) -> DeploymentState:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError("deployment state already exists")
    expected_path = _state_path_from_target(deployment_target).resolve()
    if path.resolve() != expected_path:
        raise ValueError("deployment target/path mismatch")
    state = empty_deployment_state(deployment_target)
    _atomic_write_state(path, state)
    return _load_state(path)


def _activation_id(request: CanaryActivationRequest) -> str:
    return canonical_sha256(
        {
            "p8_transaction_id": request.p8.transaction_id,
            "activation_nonce": request.activation_nonce,
            "subject": request.p8.subject.model_dump(mode="json"),
            "deployment_target": request.deployment_target,
        }
    )


def _validate_probe_age(request: CanaryActivationRequest, now: datetime) -> None:
    probed = _parse_utc(request.runtime_probe.probed_at_utc, label="probed_at_utc")
    requested = _parse_utc(request.requested_at_utc, label="requested_at_utc")
    if requested < probed:
        raise ValueError("canary request precedes runtime probe")
    age = int((now - probed).total_seconds())
    if age < 0 or age > request.policy.maximum_probe_age_seconds:
        raise ValueError("runtime probe is outside the allowed age window")


def activate_shadow_canary(
    request: CanaryActivationRequest,
    *,
    committed_at_utc: str,
) -> dict[str, Any]:
    committed_at = _parse_utc(committed_at_utc, label="committed_at_utc")
    _validate_probe_age(request, committed_at)
    state_path = _state_path_from_target(request.deployment_target)
    if state_path.is_symlink():
        raise ValueError("symbolic-link deployment state is forbidden")
    if not state_path.is_file():
        raise ValueError("deployment state does not exist")
    lock_path = state_path.with_name(f".{state_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        pre_state = _load_state(state_path)
        if pre_state.deployment_target != request.deployment_target:
            raise ValueError("deployment target differs from state")
        activation_id = _activation_id(request)
        exact_retry = (
            activation_id in pre_state.consumed_activation_ids
            and request.activation_nonce in pre_state.consumed_activation_nonces
            and pre_state.canary_binding is not None
            and pre_state.canary_binding.activation_id == activation_id
            and pre_state.canary_binding.subject == request.p8.subject
        )
        if exact_retry:
            return {
                "schema_version": "1.0",
                "status": "PASS",
                "decision": "IDEMPOTENT_ALREADY_ACTIVATED",
                "activation_id": activation_id,
                "registry_write_executed": False,
                "deployment_state_changed": False,
                "primary_binding_unchanged": True,
                "prediction_publication_allowed": False,
                "promotion_status": "CANARY_ACTIVE_NOT_PRIMARY",
                "pre_state": pre_state.model_dump(mode="json"),
                "post_state": pre_state.model_dump(mode="json"),
            }
        if pre_state.state_sha256 != request.expected_deployment_state_sha256:
            raise ValueError("stale expected deployment-state SHA-256")
        if activation_id in pre_state.consumed_activation_ids:
            raise ValueError("activation authorization was already consumed")
        if request.activation_nonce in pre_state.consumed_activation_nonces:
            raise ValueError("activation nonce was already consumed")
        if pre_state.canary_binding is not None:
            raise ValueError("a different canary is already active")
        binding = DeploymentBinding(
            subject=request.p8.subject,
            activated_at_utc=committed_at_utc,
            activation_id=activation_id,
            source_p8_transaction_id=request.p8.transaction_id,
            mode="shadow_canary",
        )
        record_payload = {
            "schema_version": "1.0",
            "generation": pre_state.generation + 1,
            "activation_id": activation_id,
            "activation_nonce": request.activation_nonce,
            "committed_at_utc": committed_at_utc,
            "previous_primary": (
                pre_state.primary_binding.model_dump(mode="json")
                if pre_state.primary_binding
                else None
            ),
            "previous_canary": None,
            "new_canary": binding.model_dump(mode="json"),
            "pre_state_sha256": pre_state.state_sha256,
        }
        record = DeploymentHistoryRecord.model_validate(
            {**record_payload, "record_sha256": canonical_sha256(record_payload)}
        )
        post_payload = {
            "schema_version": "1.0",
            "backend": pre_state.backend,
            "deployment_target": pre_state.deployment_target,
            "generation": pre_state.generation + 1,
            "primary_binding": (
                pre_state.primary_binding.model_dump(mode="json")
                if pre_state.primary_binding
                else None
            ),
            "canary_binding": binding.model_dump(mode="json"),
            "consumed_activation_ids": [
                *pre_state.consumed_activation_ids,
                activation_id,
            ],
            "consumed_activation_nonces": [
                *pre_state.consumed_activation_nonces,
                request.activation_nonce,
            ],
            "history": [
                *[item.model_dump(mode="json") for item in pre_state.history],
                record.model_dump(mode="json"),
            ],
        }
        post_state = _sealed_state(post_payload)
        _atomic_write_state(state_path, post_state)
        observed = _load_state(state_path)
        if observed != post_state:
            raise RuntimeError("post-write deployment state verification failed")
        if observed.primary_binding != pre_state.primary_binding:
            raise RuntimeError("primary binding changed during shadow activation")
        return {
            "schema_version": "1.0",
            "status": "PASS",
            "decision": "SHADOW_CANARY_ACTIVATED",
            "activation_id": activation_id,
            "registry_write_executed": False,
            "deployment_state_changed": True,
            "primary_binding_unchanged": True,
            "prediction_publication_allowed": False,
            "automatic_primary_promotion": False,
            "automatic_retraining": False,
            "automatic_rollback": False,
            "promotion_status": "CANARY_ACTIVE_NOT_PRIMARY",
            "minimum_shadow_draws": request.policy.minimum_shadow_draws,
            "pre_state": pre_state.model_dump(mode="json"),
            "post_state": post_state.model_dump(mode="json"),
        }
