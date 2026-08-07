from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class P6Operation(StrEnum):
    FIT_SERIALIZE = "fit_serialize"
    LOAD_PREDICT = "load_predict"


class P6Status(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class P6CheckState(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FailureCategory(StrEnum):
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
    UNKNOWN = "UNKNOWN"


class DistributionMode(StrEnum):
    STUDENT_T = "STUDENT_T"
    QUANTILE = "QUANTILE"
    INTRINSIC = "INTRINSIC"


class TrainerKind(StrEnum):
    LIGHTNING = "LIGHTNING"
    NATIVE_EPOCH = "NATIVE_EPOCH"


FIT_CHECKS = (
    "registry",
    "version",
    "import",
    "signature",
    "resource_policy",
    "constructor",
    "dataset",
    "fit",
    "predict",
    "shape",
    "finite",
    "device",
    "serialize",
    "artifact_integrity",
)

LOAD_CHECKS = (
    "registry",
    "version",
    "manifest",
    "artifact_integrity",
    "process_restart",
    "deserialize",
    "dataset",
    "predict",
    "shape",
    "finite",
    "device",
    "identity",
)


class P6DatasetItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(min_length=1)
    start: str = Field(min_length=1)
    target: list[float] = Field(min_length=16)
    feat_static_cat: list[int] | None = None
    feat_static_real: list[float] | None = None
    feat_dynamic_real: list[list[float]] | None = None
    past_feat_dynamic_real: list[list[float]] | None = None

    @field_validator("target", "feat_static_real")
    @classmethod
    def validate_finite_vector(cls, values: list[float] | None) -> list[float] | None:
        if values is not None and not all(math.isfinite(value) for value in values):
            raise ValueError("dataset numeric vectors must contain only finite values")
        return values

    @field_validator("feat_dynamic_real", "past_feat_dynamic_real")
    @classmethod
    def validate_finite_matrix(
        cls,
        values: list[list[float]] | None,
    ) -> list[list[float]] | None:
        if values is not None and not all(
            math.isfinite(value) for row in values for value in row
        ):
            raise ValueError("dataset numeric matrices must contain only finite values")
        return values


class ModelResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_epochs: int = Field(default=1, ge=1, le=1)
    max_batches_per_epoch: int = Field(default=1, ge=1, le=1)
    max_batch_size: int = Field(default=4, ge=1, le=4)
    max_parallel_samples: int = Field(default=4, ge=1, le=4)
    threads_per_job: int = Field(default=1, ge=1, le=1)
    device: Literal["cpu"] = "cpu"


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_class: str = Field(min_length=1)
    module_path: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    trainer_kind: TrainerKind
    distribution_mode: DistributionMode
    certified_distributions: list[str] = Field(min_length=1)
    supports_context_length: bool
    default_context_length: int = Field(ge=1)
    min_target_length: int = Field(ge=16)
    required_constructor_parameters: list[str] = Field(min_length=1)
    constructor_profile: dict[str, Any]
    resource_limits: ModelResourceLimits = Field(default_factory=ModelResourceLimits)

    @model_validator(mode="after")
    def validate_distribution_contract(self) -> ModelSpec:
        expected = {
            DistributionMode.STUDENT_T: ["StudentTOutput"],
            DistributionMode.QUANTILE: ["QuantileOutput"],
            DistributionMode.INTRINSIC: ["INTRINSIC"],
        }[self.distribution_mode]
        if self.certified_distributions != expected:
            raise ValueError("certified distributions do not match distribution mode")
        return self


class P6ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lane: Literal["compat", "latest"]
    operation: P6Operation
    model_class: str = Field(min_length=1)
    distribution_output: str | None = None
    prediction_length: int = Field(default=1, ge=1, le=8)
    context_length: int | None = Field(default=None, ge=1, le=128)
    seed: int = 1
    freq: str = Field(default="D", min_length=1)
    artifact_dir: str = Field(min_length=1)
    dataset: list[P6DatasetItem] = Field(default_factory=list)
    threads_per_job: int = Field(default=1, ge=1, le=1)
    constructor_overrides: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_operation(self) -> P6ProviderRequest:
        if self.operation is P6Operation.FIT_SERIALIZE and len(self.dataset) != 1:
            raise ValueError("fit_serialize requires exactly one dataset item")
        if self.operation is P6Operation.LOAD_PREDICT and self.dataset:
            raise ValueError("load_predict reads the immutable stored certification dataset")
        return self


class ArtifactFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class P6PredictorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    model_class: str = Field(min_length=1)
    distribution_output: str = Field(min_length=1)
    serialization_format: Literal["gluonts-predictor-directory-p6-v1"] = (
        "gluonts-predictor-directory-p6-v1"
    )
    fit_process_id: int = Field(ge=1)
    seed: int
    freq: str = Field(min_length=1)
    prediction_length: int = Field(ge=1)
    context_length: int | None = Field(default=None, ge=1)
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    constructor_arguments_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pre_reload_prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_versions: dict[str, str | None] = Field(default_factory=dict)
    files: list[ArtifactFile] = Field(min_length=1)
    tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_files(self) -> P6PredictorManifest:
        paths = [entry.relative_path for entry in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("predictor manifest contains duplicate paths")
        if any(path.startswith("/") or ".." in Path(path).parts for path in paths):
            raise ValueError("predictor manifest paths must be safe relative paths")
        if artifact_tree_sha256(self.files) != self.tree_sha256:
            raise ValueError("predictor manifest tree SHA-256 mismatch")
        return self


class P6StageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    operation: P6Operation
    model_class: str = Field(min_length=1)
    distribution_output: str = Field(min_length=1)
    status: P6Status
    process_id: int = Field(ge=1)
    fit_process_id: int | None = Field(default=None, ge=1)
    prediction_length: int = Field(ge=1)
    expected_shape: list[int]
    observed_shape: list[int] | None = None
    prediction_values: list[float] = Field(default_factory=list)
    observed_devices: list[str] = Field(default_factory=list)
    artifact_manifest: P6PredictorManifest | None = None
    artifact_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    failure_category: FailureCategory | None = None
    checks: dict[str, P6CheckState]
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prediction_values")
    @classmethod
    def validate_predictions(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("stage prediction values must be finite")
        return values

    @model_validator(mode="after")
    def validate_stage(self) -> P6StageEvidence:
        required = FIT_CHECKS if self.operation is P6Operation.FIT_SERIALIZE else LOAD_CHECKS
        missing = [name for name in required if name not in self.checks]
        if missing:
            raise ValueError(f"missing stage checks: {missing}")
        if self.status is not P6Status.VERIFIED:
            if not self.errors or self.failure_category is None:
                raise ValueError("non-VERIFIED stage evidence requires error classification")
            return self
        if self.errors or self.failure_category is not None:
            raise ValueError("VERIFIED stage evidence cannot contain failure details")
        if any(self.checks[name] is not P6CheckState.PASS for name in required):
            raise ValueError("VERIFIED stage evidence requires all stage checks to PASS")
        if self.observed_shape != self.expected_shape:
            raise ValueError("VERIFIED stage output shape mismatch")
        if len(self.prediction_values) != self.prediction_length:
            raise ValueError("VERIFIED stage prediction length mismatch")
        if not self.observed_devices or any(
            not device.startswith("cpu") for device in self.observed_devices
        ):
            raise ValueError("VERIFIED stage requires observed CPU parameters")
        if self.artifact_manifest_sha256 is None:
            raise ValueError("VERIFIED stage requires artifact manifest identity")
        if self.operation is P6Operation.FIT_SERIALIZE:
            if self.artifact_manifest is None:
                raise ValueError("VERIFIED fit stage requires artifact manifest")
            if manifest_sha256(self.artifact_manifest) != self.artifact_manifest_sha256:
                raise ValueError("fit stage artifact manifest SHA-256 mismatch")
        else:
            if self.fit_process_id is None or self.fit_process_id == self.process_id:
                raise ValueError("VERIFIED load stage requires a distinct fit process")
        return self


class P6ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lane: Literal["compat", "latest"]
    status: P6Status
    evidence: P6StageEvidence
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_response(self) -> P6ProviderResponse:
        if self.evidence.lane != self.lane or self.evidence.status != self.status:
            raise ValueError("provider response and evidence identity mismatch")
        if self.status is P6Status.VERIFIED and self.errors:
            raise ValueError("VERIFIED provider response cannot contain errors")
        if self.status is not P6Status.VERIFIED and not self.errors:
            raise ValueError("non-VERIFIED provider response requires errors")
        return self


class P6ModelLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_class: str = Field(min_length=1)
    status: P6Status
    fit: P6ProviderResponse
    reload: P6ProviderResponse | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> P6ModelLifecycle:
        if self.fit.evidence.model_class != self.model_class:
            raise ValueError("fit evidence model identity mismatch")
        if self.reload is not None and self.reload.evidence.model_class != self.model_class:
            raise ValueError("reload evidence model identity mismatch")
        if self.status is P6Status.VERIFIED:
            if self.errors:
                raise ValueError("VERIFIED model lifecycle cannot contain errors")
            if self.fit.status is not P6Status.VERIFIED:
                raise ValueError("VERIFIED lifecycle requires VERIFIED fit")
            if self.reload is None or self.reload.status is not P6Status.VERIFIED:
                raise ValueError("VERIFIED lifecycle requires VERIFIED reload")
            fit_sha = self.fit.evidence.artifact_manifest_sha256
            load_sha = self.reload.evidence.artifact_manifest_sha256
            if fit_sha is None or fit_sha != load_sha:
                raise ValueError("lifecycle artifact manifest identity mismatch")
        elif not self.errors:
            raise ValueError("non-VERIFIED model lifecycle requires errors")
        return self


class P6CampaignResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    lane: Literal["compat", "latest"]
    status: P6Status
    workers: int = Field(ge=1, le=8)
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    models: list[P6ModelLifecycle] = Field(min_length=9, max_length=9)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_campaign(self) -> P6CampaignResult:
        names = [model.model_class for model in self.models]
        if len(names) != len(set(names)):
            raise ValueError("campaign contains duplicate model lifecycles")
        if self.status is P6Status.VERIFIED:
            if self.errors or any(
                model.status is not P6Status.VERIFIED for model in self.models
            ):
                raise ValueError("VERIFIED campaign requires all nine models VERIFIED")
        elif not self.errors:
            raise ValueError("non-VERIFIED campaign requires errors")
        return self


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def prediction_sha256(values: list[float]) -> str:
    return sha256_json([float(value) for value in values])


def artifact_tree_sha256(files: list[ArtifactFile]) -> str:
    return sha256_json(
        [
            entry.model_dump(mode="json")
            for entry in sorted(files, key=lambda item: item.relative_path)
        ]
    )


def manifest_sha256(manifest: P6PredictorManifest) -> str:
    return sha256_json(manifest.model_dump(mode="json"))


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
    return hashlib.sha256(content).hexdigest()
