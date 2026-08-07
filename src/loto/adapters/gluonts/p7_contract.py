from __future__ import annotations

import hashlib
import json
import os
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceState(StrEnum):
    VALID = "VALID"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


class CertificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    NOT_EVALUATED = "NOT_EVALUATED"


class P7FailureCategory(StrEnum):
    BOOTSTRAP_FAILED = "BOOTSTRAP_FAILED"
    MISSING_ARTIFACT = "MISSING_ARTIFACT"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    CHECKSUM_INVENTORY_MISMATCH = "CHECKSUM_INVENTORY_MISMATCH"
    MANIFEST_MISMATCH = "MANIFEST_MISMATCH"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
    LOCKFILE_MISMATCH = "LOCKFILE_MISMATCH"
    REGISTRY_MISMATCH = "REGISTRY_MISMATCH"
    MODEL_SET_MISMATCH = "MODEL_SET_MISMATCH"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    MODEL_UNSUPPORTED = "MODEL_UNSUPPORTED"
    DISTRIBUTION_UNSUPPORTED = "DISTRIBUTION_UNSUPPORTED"
    SIGNATURE_MISMATCH = "SIGNATURE_MISMATCH"
    UNSUPPORTED_ARGUMENT = "UNSUPPORTED_ARGUMENT"
    RESOURCE_POLICY_VIOLATION = "RESOURCE_POLICY_VIOLATION"
    IMPORT_FAILED = "IMPORT_FAILED"
    CONSTRUCTOR_FAILED = "CONSTRUCTOR_FAILED"
    DATASET_FAILED = "DATASET_FAILED"
    FIT_FAILED = "FIT_FAILED"
    PREDICT_FAILED = "PREDICT_FAILED"
    OUTPUT_SHAPE_FAILED = "OUTPUT_SHAPE_FAILED"
    NON_FINITE_OUTPUT = "NON_FINITE_OUTPUT"
    DEVICE_MISMATCH = "DEVICE_MISMATCH"
    SERIALIZE_FAILED = "SERIALIZE_FAILED"
    ARTIFACT_INTEGRITY_FAILED = "ARTIFACT_INTEGRITY_FAILED"
    PROCESS_RESTART_REQUIRED = "PROCESS_RESTART_REQUIRED"
    DESERIALIZE_FAILED = "DESERIALIZE_FAILED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    PROVIDER_CRASH = "PROVIDER_CRASH"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class P7ModelClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lane: Literal["compat", "latest"]
    model_class: str = Field(min_length=1)
    certification_status: CertificationStatus
    failed_stage: Literal["fit_serialize", "load_predict", "campaign", "none"]
    failure_category: P7FailureCategory | None = None
    errors: list[str] = Field(default_factory=list)
    fit_status: str = Field(min_length=1)
    reload_status: str | None = None
    artifact_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    fit_process_id: int | None = Field(default=None, ge=1)
    load_process_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_classification(self) -> P7ModelClassification:
        if self.certification_status is CertificationStatus.VERIFIED:
            if self.failed_stage != "none" or self.failure_category is not None:
                raise ValueError("VERIFIED model cannot contain failure classification")
            if self.errors:
                raise ValueError("VERIFIED model cannot contain errors")
            if self.fit_status != "VERIFIED" or self.reload_status != "VERIFIED":
                raise ValueError("VERIFIED model requires both stages VERIFIED")
            if self.artifact_manifest_sha256 is None:
                raise ValueError("VERIFIED model requires artifact manifest identity")
            if self.fit_process_id is None or self.load_process_id is None:
                raise ValueError("VERIFIED model requires process evidence")
            if self.fit_process_id == self.load_process_id:
                raise ValueError("VERIFIED model requires a process restart")
        elif self.failure_category is None or not self.errors:
            raise ValueError("non-VERIFIED model requires classified errors")
        return self


class P7LaneAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    bootstrap_return_code: int
    evidence_state: EvidenceState
    certification_status: CertificationStatus
    run_id: str | None = None
    registry_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    campaign_result_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    campaign_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    provenance_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checksum_file_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    runtime_versions: dict[str, str | None] = Field(default_factory=dict)
    models: list[P7ModelClassification] = Field(default_factory=list)
    failure_categories: list[P7FailureCategory] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lane(self) -> P7LaneAudit:
        if self.evidence_state is EvidenceState.VALID:
            if len(self.models) != 9:
                raise ValueError("valid lane evidence requires exactly nine models")
            names = [model.model_class for model in self.models]
            if len(names) != len(set(names)):
                raise ValueError("lane audit contains duplicate models")
            if not all(
                (
                    self.run_id,
                    self.registry_sha256,
                    self.campaign_result_sha256,
                    self.campaign_manifest_sha256,
                    self.provenance_sha256,
                    self.checksum_file_sha256,
                )
            ):
                raise ValueError("valid lane evidence requires all artifact identities")
        if self.certification_status is CertificationStatus.VERIFIED:
            if self.evidence_state is not EvidenceState.VALID:
                raise ValueError("VERIFIED lane requires valid evidence")
            if any(
                model.certification_status is not CertificationStatus.VERIFIED
                for model in self.models
            ):
                raise ValueError("VERIFIED lane requires all nine models VERIFIED")
            if self.errors or self.failure_categories:
                raise ValueError("VERIFIED lane cannot contain failures")
        elif not self.errors:
            raise ValueError("non-VERIFIED lane requires errors")
        return self


class P7TargetMachineAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    phase: Literal["P7_TARGET_MACHINE_EXECUTION"] = "P7_TARGET_MACHINE_EXECUTION"
    run_id: str = Field(min_length=1)
    evidence_state: EvidenceState
    certification_status: CertificationStatus
    compat: P7LaneAudit
    latest: P7LaneAudit
    registry_match: bool
    model_set_match: bool
    verified_model_lifecycles: int = Field(ge=0, le=18)
    failure_counts: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_target_audit(self) -> P7TargetMachineAudit:
        if self.compat.lane != "compat" or self.latest.lane != "latest":
            raise ValueError("target audit lane identity mismatch")
        if self.certification_status is CertificationStatus.VERIFIED:
            if self.evidence_state is not EvidenceState.VALID:
                raise ValueError("VERIFIED target audit requires valid evidence")
            if not self.registry_match or not self.model_set_match:
                raise ValueError("VERIFIED target audit requires cross-lane identity")
            if self.verified_model_lifecycles != 18:
                raise ValueError("VERIFIED target audit requires 18 model-lane lifecycles")
            if self.errors or self.failure_counts:
                raise ValueError("VERIFIED target audit cannot contain failures")
        elif not self.errors:
            raise ValueError("non-VERIFIED target audit requires errors")
        return self


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def atomic_write_json(path: Path, payload: Any) -> str:
    content = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256_bytes(content)
