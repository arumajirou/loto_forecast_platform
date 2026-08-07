"""Strict provider-neutral contracts for runtime-certification evidence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .statuses import (
    AccuracyStatus,
    CertificationProfile,
    EvidenceOrigin,
    FailurePhase,
    RuntimeStatus,
)

RUNTIME_CERTIFICATION_SCHEMA_VERSION = "1.0.0"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def contains_control_characters(value: str) -> bool:
    """Return whether text contains C0 or DEL control characters."""
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )


class RequestIdentity(StrictModel):
    request_id: str = Field(min_length=1, max_length=256)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    seed: int = Field(ge=0, le=2_147_483_647)
    requested_device: Literal["cpu", "cuda"]
    input_schema_id: str = Field(min_length=1, max_length=256)


class PackageIdentity(StrictModel):
    distribution: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=128)
    artifact_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_revision: str | None = Field(default=None, min_length=1, max_length=256)


class ModelIdentity(StrictModel):
    model_id: str = Field(min_length=1, max_length=256)
    repository_id: str = Field(min_length=1, max_length=512)
    revision: str = Field(min_length=1, max_length=256)
    config_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    weight_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class ArtifactIdentity(StrictModel):
    relative_path: str = Field(min_length=1, max_length=4096)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    role: str = Field(min_length=1, max_length=128)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or value.startswith(("/", "\\")):
            raise ValueError("artifact path must be relative")
        if "\\" in value or ":" in value:
            raise ValueError("artifact path must use canonical POSIX syntax")
        if contains_control_characters(value):
            raise ValueError("artifact path must not contain control characters")
        if any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("artifact path contains an unsafe component")
        return value


class SnapshotIdentity(StrictModel):
    snapshot_root: str = Field(min_length=1, max_length=4096)
    expected_revision: str = Field(min_length=1, max_length=256)
    artifacts: list[ArtifactIdentity] = Field(min_length=1)

    @field_validator("artifacts")
    @classmethod
    def unique_artifacts(cls, value: list[ArtifactIdentity]) -> list[ArtifactIdentity]:
        paths = [item.relative_path for item in value]
        if len(paths) != len(set(paths)):
            raise ValueError("snapshot artifact paths must be unique")
        if len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("snapshot artifact paths must not collide case-insensitively")
        return value


class CommandSpec(StrictModel):
    argv: list[str] = Field(min_length=1)
    cwd: str = Field(min_length=1, max_length=4096)
    timeout_seconds: float = Field(gt=0.0, le=86_400.0)
    environment: dict[str, str] = Field(default_factory=dict)

    @field_validator("argv")
    @classmethod
    def non_empty_argv(cls, value: list[str]) -> list[str]:
        if any(not item for item in value):
            raise ValueError("command arguments must not be empty")
        return value


class ProcessExecution(StrictModel):
    run_label: str = Field(min_length=1, max_length=128)
    process_pid: int | None = Field(default=None, ge=1)
    started_at_utc: datetime
    finished_at_utc: datetime
    exit_code: int | None = None
    timed_out: bool = False
    stdout_sha256: str = Field(pattern=SHA256_PATTERN)
    stderr_sha256: str = Field(pattern=SHA256_PATTERN)
    response_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_process_state(self) -> ProcessExecution:
        if self.started_at_utc.utcoffset() is None or self.finished_at_utc.utcoffset() is None:
            raise ValueError("process timestamps must be timezone-aware")
        if self.finished_at_utc < self.started_at_utc:
            raise ValueError("process finish time precedes start time")
        if self.timed_out and self.exit_code is not None:
            raise ValueError("timed-out process must not claim an exit code")
        if not self.timed_out and self.exit_code is None:
            raise ValueError("completed process requires an exit code")
        return self


class OutputContract(StrictModel):
    expected_shape: list[int] = Field(min_length=1)
    quantile_axis: int | None = Field(default=None, ge=0)
    quantile_levels: list[float] = Field(default_factory=list)
    monotonic_tolerance: float = Field(default=0.0, ge=0.0)

    @field_validator("expected_shape")
    @classmethod
    def positive_shape(cls, value: list[int]) -> list[int]:
        if any(item < 1 for item in value):
            raise ValueError("expected_shape dimensions must be positive")
        return value

    @field_validator("quantile_levels")
    @classmethod
    def increasing_quantiles(cls, value: list[float]) -> list[float]:
        if any(not 0.0 < item < 1.0 for item in value):
            raise ValueError("quantile levels must lie in (0, 1)")
        if value != sorted(set(value)):
            raise ValueError("quantile levels must be unique and strictly increasing")
        return value

    @model_validator(mode="after")
    def validate_quantile_axis(self) -> OutputContract:
        if self.quantile_axis is None and self.quantile_levels:
            raise ValueError("quantile levels require quantile_axis")
        if self.quantile_axis is not None:
            if self.quantile_axis >= len(self.expected_shape):
                raise ValueError("quantile_axis is outside expected_shape")
            if len(self.quantile_levels) != self.expected_shape[self.quantile_axis]:
                raise ValueError("quantile level count must match the quantile axis")
        return self


class OutputEvidence(StrictModel):
    observed_shape: list[int] = Field(min_length=1)
    finite: bool
    quantile_monotonic: bool | None = None
    output_sha256: str = Field(pattern=SHA256_PATTERN)


class GPUProcessSample(StrictModel):
    provider_pid: int = Field(ge=1)
    gpu_uuid: str = Field(min_length=1, max_length=256)
    used_memory_bytes: int = Field(gt=0)
    observed_at_utc: datetime

    @field_validator("observed_at_utc")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("GPU sample timestamp must be timezone-aware")
        return value


class DeviceEvidence(StrictModel):
    requested_device: Literal["cpu", "cuda"]
    effective_device: Literal["cpu", "cuda"]
    cpu_fallback: bool
    provider_pid: int = Field(ge=1)
    provider_gpu_pid: int | None = Field(default=None, ge=1)
    gpu_uuid: str | None = Field(default=None, min_length=1, max_length=256)
    peak_vram_bytes: int = Field(default=0, ge=0)
    external_gpu_samples: list[GPUProcessSample] = Field(default_factory=list)
    pid_released_after_exit: bool
    origin: EvidenceOrigin

    @model_validator(mode="after")
    def validate_device_contract(self) -> DeviceEvidence:
        if self.effective_device != self.requested_device:
            raise ValueError("requested and effective devices differ")
        if self.cpu_fallback:
            raise ValueError("CPU fallback is not certifiable")
        if self.requested_device == "cpu":
            if self.provider_gpu_pid is not None or self.gpu_uuid is not None:
                raise ValueError("CPU evidence must not report a GPU identity")
            if self.peak_vram_bytes != 0 or self.external_gpu_samples:
                raise ValueError("CPU evidence must not report GPU memory samples")
        else:
            if self.provider_gpu_pid != self.provider_pid:
                raise ValueError("GPU PID must equal provider PID")
            if self.gpu_uuid is None or self.peak_vram_bytes <= 0:
                raise ValueError("CUDA evidence requires GPU UUID and positive VRAM")
            matching = [
                sample
                for sample in self.external_gpu_samples
                if sample.provider_pid == self.provider_pid
                and sample.gpu_uuid == self.gpu_uuid
            ]
            if not matching:
                raise ValueError("CUDA evidence requires an external matching GPU sample")
            if not self.pid_released_after_exit:
                raise ValueError("CUDA provider PID must be released after exit")
        return self


class ReplayEvidence(StrictModel):
    save_succeeded: bool
    reload_succeeded: bool
    re_predict_succeeded: bool
    distinct_processes: bool
    first_process_pid: int = Field(ge=1)
    second_process_pid: int = Field(ge=1)
    first_output_sha256: str = Field(pattern=SHA256_PATTERN)
    second_output_sha256: str = Field(pattern=SHA256_PATTERN)
    exact_match: bool
    maximum_absolute_difference: float = Field(ge=0.0)
    tolerance: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_replay(self) -> ReplayEvidence:
        if self.distinct_processes != (self.first_process_pid != self.second_process_pid):
            raise ValueError("distinct_processes disagrees with process IDs")
        if self.exact_match != (self.first_output_sha256 == self.second_output_sha256):
            raise ValueError("exact_match disagrees with output hashes")
        if not self.exact_match and self.maximum_absolute_difference > self.tolerance:
            raise ValueError("non-exact replay exceeds tolerance")
        return self


class RuntimeCheckSummary(StrictModel):
    load_success: bool
    input_validation_success: bool
    inference_success: bool
    process_exit_success: bool
    output: OutputEvidence
    device: DeviceEvidence
    replay: ReplayEvidence


class CertificationReport(StrictModel):
    schema_version: Literal["1.0.0"] = RUNTIME_CERTIFICATION_SCHEMA_VERSION
    certification_id: str = Field(min_length=1, max_length=256)
    profile: CertificationProfile
    evidence_origin: EvidenceOrigin
    runtime_status: RuntimeStatus
    accuracy_status: AccuracyStatus = AccuracyStatus.NOT_EVALUATED
    request: RequestIdentity
    package: PackageIdentity
    model: ModelIdentity
    snapshot: SnapshotIdentity
    process_runs: list[ProcessExecution] = Field(min_length=2)
    checks: RuntimeCheckSummary
    artifacts: list[ArtifactIdentity] = Field(default_factory=list)
    failure_phase: FailurePhase | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def validate_status_boundary(self) -> CertificationReport:
        if self.snapshot.expected_revision != self.model.revision:
            raise ValueError("model revision and snapshot revision disagree")
        if self.checks.device.origin != self.evidence_origin:
            raise ValueError("device evidence origin must equal report evidence origin")
        if self.request.requested_device != self.checks.device.requested_device:
            raise ValueError("request and device evidence disagree")
        labels = [run.run_label for run in self.process_runs]
        if len(labels) != len(set(labels)):
            raise ValueError("process run labels must be unique")
        if self.runtime_status == RuntimeStatus.RUNTIME_CERTIFIED:
            if self.evidence_origin != EvidenceOrigin.REAL:
                raise ValueError("synthetic or injected evidence cannot be runtime certified")
            if self.profile == CertificationProfile.GPU_FORMAL:
                if self.checks.device.requested_device != "cuda":
                    raise ValueError("GPU_FORMAL requires a CUDA request")
            elif self.checks.device.requested_device != "cpu":
                raise ValueError("CPU_SMOKE requires a CPU request")
            if not all(
                (
                    self.checks.load_success,
                    self.checks.input_validation_success,
                    self.checks.inference_success,
                    self.checks.process_exit_success,
                    self.checks.output.finite,
                    self.checks.output.quantile_monotonic is not False,
                    self.checks.replay.save_succeeded,
                    self.checks.replay.reload_succeeded,
                    self.checks.replay.re_predict_succeeded,
                    self.checks.replay.distinct_processes,
                )
            ):
                raise ValueError("RUNTIME_CERTIFIED requires every runtime check")
            if self.failure_phase is not None or self.failure_reason is not None:
                raise ValueError("RUNTIME_CERTIFIED cannot include failure fields")
        if self.evidence_origin != EvidenceOrigin.REAL:
            if self.runtime_status not in {
                RuntimeStatus.PARTIALLY_VERIFIED,
                RuntimeStatus.FAILED,
                RuntimeStatus.BLOCKED,
            }:
                raise ValueError("non-real evidence must remain partial, failed, or blocked")
        if self.runtime_status in {RuntimeStatus.FAILED, RuntimeStatus.BLOCKED}:
            if self.failure_phase is None or not self.failure_reason:
                raise ValueError("failed or blocked reports require failure evidence")
        return self
