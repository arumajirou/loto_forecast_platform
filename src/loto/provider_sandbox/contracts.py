"""Strict immutable contracts for untrusted provider sandboxing."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import sha256_canonical

SCHEMA_VERSION = "1.0.0"
SafeIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
AbsolutePath = Annotated[str, Field(min_length=1, max_length=4096, pattern=r"^/[^\x00]*$")]
EnvName = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Z_][A-Z0-9_]*$")]
DenyPattern = Annotated[str, Field(min_length=1, max_length=128)]


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )


class SandboxBackend(str, Enum):
    BUBBLEWRAP = "BUBBLEWRAP"
    ROOTLESS_OCI = "ROOTLESS_OCI"
    NONE = "NONE"


class NetworkMode(str, Enum):
    DISABLED = "DISABLED"


class RootFilesystemMode(str, Enum):
    READ_ONLY = "READ_ONLY"


class MountMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    READ_WRITE_TMP = "READ_WRITE_TMP"


class MountKind(str, Enum):
    RUNTIME = "RUNTIME"
    REPOSITORY = "REPOSITORY"
    MODEL_SNAPSHOT = "MODEL_SNAPSHOT"
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    TMPFS = "TMPFS"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    INCOMPLETE = "INCOMPLETE"


class ProcessOutcome(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    NONZERO_EXIT = "NONZERO_EXIT"
    TIMED_OUT = "TIMED_OUT"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    LAUNCH_FAILED = "LAUNCH_FAILED"


class SandboxMount(StrictFrozenModel):
    mount_id: SafeIdentifier
    kind: MountKind
    mode: MountMode
    source_path: AbsolutePath | None = None
    target_path: AbsolutePath
    source_sha256: Sha256 | None = None
    required: bool = True

    @model_validator(mode="after")
    def validate_kind_mode(self) -> "SandboxMount":
        writable = {MountKind.OUTPUT, MountKind.TMPFS}
        if self.kind in writable and self.mode != MountMode.READ_WRITE_TMP:
            raise ValueError("OUTPUT and TMPFS mounts must be READ_WRITE_TMP")
        if self.kind not in writable and self.mode != MountMode.READ_ONLY:
            raise ValueError("repository, model and input mounts must be READ_ONLY")
        if self.kind == MountKind.TMPFS:
            if self.source_path is not None or self.source_sha256 is not None:
                raise ValueError("TMPFS mount cannot have a source path or hash")
        elif self.source_path is None:
            raise ValueError("non-TMPFS mount requires source_path")
        return self


class ResourceLimits(StrictFrozenModel):
    pids: PositiveInt
    cpu_cores: Annotated[float, Field(gt=0, le=256)]
    memory_bytes: PositiveInt
    file_size_bytes: PositiveInt
    output_bytes: PositiveInt
    wall_timeout_seconds: Annotated[float, Field(gt=0, le=86400)]


class SandboxPolicy(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    policy_id: SafeIdentifier
    backend: SandboxBackend
    untrusted_remote_code: bool
    network_mode: Literal[NetworkMode.DISABLED] = NetworkMode.DISABLED
    root_filesystem: Literal[RootFilesystemMode.READ_ONLY] = RootFilesystemMode.READ_ONLY
    no_new_privileges: Literal[True] = True
    drop_all_capabilities: Literal[True] = True
    mounts: tuple[SandboxMount, ...]
    environment_allowlist: tuple[EnvName, ...]
    environment_deny_patterns: tuple[DenyPattern, ...]
    executable_allowlist: tuple[AbsolutePath, ...]
    gpu_device_allowlist: tuple[SafeIdentifier, ...] = ()
    limits: ResourceLimits
    oci_image: str | None = None
    policy_sha256: Sha256

    @model_validator(mode="after")
    def policy_consistency(self) -> "SandboxPolicy":
        if self.untrusted_remote_code and self.backend == SandboxBackend.NONE:
            raise ValueError("backend NONE is forbidden for untrusted remote code")
        if len({item.mount_id for item in self.mounts}) != len(self.mounts):
            raise ValueError("mount_id values must be unique")
        if len({item.target_path for item in self.mounts}) != len(self.mounts):
            raise ValueError("mount target paths must be unique")
        for values, label in (
            (self.environment_allowlist, "environment allowlist"),
            (self.environment_deny_patterns, "environment deny patterns"),
            (self.executable_allowlist, "executable allowlist"),
            (self.gpu_device_allowlist, "GPU device allowlist"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
        for pattern in self.environment_deny_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError("environment deny pattern must be valid regex") from exc
        if self.backend == SandboxBackend.ROOTLESS_OCI:
            if self.oci_image is None or "@sha256:" not in self.oci_image:
                raise ValueError("ROOTLESS_OCI requires a digest-pinned image")
        elif self.oci_image is not None:
            raise ValueError("oci_image is valid only for ROOTLESS_OCI")
        expected = self.calculate_sha256()
        if self.policy_sha256 != expected:
            raise ValueError("policy_sha256 mismatch")
        return self

    def calculate_sha256(self) -> str:
        return sha256_canonical(self.model_dump(mode="python", exclude={"policy_sha256"}))

    @classmethod
    def create(cls, **values: object) -> "SandboxPolicy":
        payload = {
            "schema_version": SCHEMA_VERSION,
            "network_mode": NetworkMode.DISABLED,
            "root_filesystem": RootFilesystemMode.READ_ONLY,
            "no_new_privileges": True,
            "drop_all_capabilities": True,
            "gpu_device_allowlist": (),
            "oci_image": None,
            **values,
        }
        return cls(policy_sha256=sha256_canonical(payload), **payload)


class SandboxExecutionRequest(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    request_id: SafeIdentifier
    run_id: SafeIdentifier
    executable: AbsolutePath
    arguments: tuple[str, ...] = ()
    environment: dict[EnvName, str] = Field(default_factory=dict)
    requested_gpu_devices: tuple[SafeIdentifier, ...] = ()
    issued_at: datetime

    @field_validator("issued_at")
    @classmethod
    def issued_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("issued_at must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def validate_arguments(self) -> "SandboxExecutionRequest":
        if len(set(self.requested_gpu_devices)) != len(self.requested_gpu_devices):
            raise ValueError("requested GPU devices must be unique")
        for argument in self.arguments:
            if "\x00" in argument:
                raise ValueError("arguments cannot contain NUL")
            if len(argument) > 4096:
                raise ValueError("argument exceeds 4096 characters")
        for value in self.environment.values():
            if "\x00" in value or "\n" in value or "\r" in value:
                raise ValueError("environment values cannot contain control separators")
            if len(value) > 4096:
                raise ValueError("environment value exceeds 4096 characters")
        return self


class BackendEvidence(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    backend: SandboxBackend
    available: bool
    executable_path: AbsolutePath | None = None
    executable_sha256: Sha256 | None = None
    version: str | None = Field(default=None, max_length=256)
    rootless: bool | None = None
    detected_at: datetime

    @field_validator("detected_at")
    @classmethod
    def detected_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("detected_at must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def evidence_consistency(self) -> "BackendEvidence":
        if self.available and (self.executable_path is None or self.executable_sha256 is None):
            raise ValueError("available backend requires executable path and hash")
        if not self.available and any(
            value is not None
            for value in (self.executable_path, self.executable_sha256, self.version)
        ):
            raise ValueError("unavailable backend cannot claim executable identity")
        if (
            self.backend == SandboxBackend.ROOTLESS_OCI
            and self.available
            and self.rootless is not True
        ):
            raise ValueError("ROOTLESS_OCI evidence must prove rootless execution")
        return self


class SandboxArgvPlan(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    backend: SandboxBackend
    argv: tuple[str, ...]
    environment_keys: tuple[EnvName, ...]
    plan_sha256: Sha256

    @model_validator(mode="after")
    def verify_plan_hash(self) -> "SandboxArgvPlan":
        expected = sha256_canonical(
            self.model_dump(mode="python", exclude={"plan_sha256"})
        )
        if self.plan_sha256 != expected:
            raise ValueError("plan_sha256 mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        backend: SandboxBackend,
        argv: tuple[str, ...],
        environment_keys: tuple[str, ...],
    ) -> "SandboxArgvPlan":
        payload = {
            "schema_version": SCHEMA_VERSION,
            "backend": backend,
            "argv": argv,
            "environment_keys": environment_keys,
        }
        return cls(plan_sha256=sha256_canonical(payload), **payload)


class EffectiveMountEvidence(StrictFrozenModel):
    mount_id: SafeIdentifier
    kind: MountKind
    mode: MountMode
    target_path: AbsolutePath
    source_path_sha256: Sha256 | None = None


class EffectiveSandboxEvidence(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    backend: SandboxBackend | None
    network_disabled: bool | None
    root_read_only: bool | None
    no_new_privileges: bool | None
    all_capabilities_dropped: bool | None
    limits: ResourceLimits | None
    mounts: tuple[EffectiveMountEvidence, ...] | None
    environment_keys: tuple[EnvName, ...] | None
    gpu_devices: tuple[SafeIdentifier, ...] | None
    observed_at: datetime
    evidence_sha256: Sha256

    @field_validator("observed_at")
    @classmethod
    def observed_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("observed_at must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def verify_hash(self) -> "EffectiveSandboxEvidence":
        expected = sha256_canonical(
            self.model_dump(mode="python", exclude={"evidence_sha256"})
        )
        if self.evidence_sha256 != expected:
            raise ValueError("effective evidence hash mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> "EffectiveSandboxEvidence":
        payload = {"schema_version": SCHEMA_VERSION, **values}
        return cls(evidence_sha256=sha256_canonical(payload), **payload)


class SandboxVerificationReport(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: VerificationStatus
    verified: bool
    policy_sha256: Sha256
    effective_evidence_sha256: Sha256
    missing_checks: tuple[SafeIdentifier, ...]
    mismatches: tuple[SafeIdentifier, ...]
    report_sha256: Sha256

    @model_validator(mode="after")
    def verify_report(self) -> "SandboxVerificationReport":
        if self.verified != (self.status == VerificationStatus.VERIFIED):
            raise ValueError("verified flag must match status")
        if self.status == VerificationStatus.VERIFIED and (
            self.missing_checks or self.mismatches
        ):
            raise ValueError("verified report cannot contain gaps")
        expected = sha256_canonical(
            self.model_dump(mode="python", exclude={"report_sha256"})
        )
        if self.report_sha256 != expected:
            raise ValueError("verification report hash mismatch")
        return self


class SandboxProcessResult(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    outcome: ProcessOutcome
    pid: PositiveInt | None
    exit_code: int | None
    timed_out: bool
    duration_ms: NonNegativeInt
    stdout_sha256: Sha256
    stdout_size_bytes: NonNegativeInt
    stderr_sha256: Sha256
    stderr_size_bytes: NonNegativeInt
    error_code: SafeIdentifier | None = None
    result_sha256: Sha256

    @model_validator(mode="after")
    def verify_result_hash(self) -> "SandboxProcessResult":
        if self.outcome == ProcessOutcome.TIMED_OUT and not self.timed_out:
            raise ValueError("TIMED_OUT result requires timed_out=true")
        expected = sha256_canonical(
            self.model_dump(mode="python", exclude={"result_sha256"})
        )
        if self.result_sha256 != expected:
            raise ValueError("process result hash mismatch")
        return self
