from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LifecycleOutcome(StrEnum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class LifecycleCheckState(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


FIT_REQUIRED_CHECKS = (
    "version",
    "import",
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

RELOAD_REQUIRED_CHECKS = (
    "manifest",
    "artifact_integrity",
    "process_restart",
    "version",
    "deserialize",
    "dataset",
    "predict",
    "shape",
    "finite",
    "device",
    "identity",
)


class ArtifactFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PredictorArtifactManifest(BaseModel):
    """Immutable identity and integrity record for one serialized Predictor directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    model_class: Literal["DeepAREstimator"] = "DeepAREstimator"
    serialization_format: Literal["gluonts-predictor-directory-v1"] = (
        "gluonts-predictor-directory-v1"
    )
    created_at_utc: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    fit_process_id: int = Field(ge=1)
    seed: int
    freq: str = Field(min_length=1)
    prediction_length: int = Field(ge=1)
    context_length: int = Field(ge=1)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pre_reload_prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_versions: dict[str, str | None] = Field(default_factory=dict)
    files: list[ArtifactFile] = Field(min_length=1)
    tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_file_tree(self) -> PredictorArtifactManifest:
        relative_paths = [entry.relative_path for entry in self.files]
        if len(relative_paths) != len(set(relative_paths)):
            raise ValueError("predictor artifact manifest contains duplicate paths")
        if any(
            path.startswith("/") or ".." in Path(path).parts
            for path in relative_paths
        ):
            raise ValueError("predictor artifact paths must be safe relative paths")
        calculated = artifact_tree_sha256(self.files)
        if self.tree_sha256 != calculated:
            raise ValueError("predictor artifact tree SHA-256 does not match files")
        return self


class PredictorFitSerializeResult(BaseModel):
    """Fit, predict, and serialize evidence produced by the training process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    outcome: LifecycleOutcome
    process_id: int = Field(ge=1)
    seed: int
    prediction_length: int = Field(ge=1)
    context_length: int = Field(ge=1)
    expected_shape: list[int]
    observed_shape: list[int] | None = None
    prediction_values: list[float] = Field(default_factory=list)
    observed_devices: list[str] = Field(default_factory=list)
    artifact_manifest: PredictorArtifactManifest | None = None
    artifact_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    checks: dict[str, LifecycleCheckState]
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prediction_values")
    @classmethod
    def validate_prediction_values(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("fit/serialize predictions must be finite")
        return values

    @model_validator(mode="after")
    def validate_outcome(self) -> PredictorFitSerializeResult:
        missing = [name for name in FIT_REQUIRED_CHECKS if name not in self.checks]
        if missing:
            raise ValueError(f"missing fit/serialize checks: {missing}")
        if self.outcome is not LifecycleOutcome.VERIFIED:
            if not self.errors:
                raise ValueError("non-VERIFIED fit/serialize results require errors")
            return self
        if self.errors:
            raise ValueError("VERIFIED fit/serialize results cannot contain errors")
        if any(
            self.checks[name] is not LifecycleCheckState.PASS
            for name in FIT_REQUIRED_CHECKS
        ):
            raise ValueError("VERIFIED fit/serialize requires every check to PASS")
        if self.observed_shape != self.expected_shape:
            raise ValueError("fit/serialize shape mismatch")
        if len(self.prediction_values) != self.prediction_length:
            raise ValueError("fit/serialize prediction length mismatch")
        if not self.observed_devices or any(
            not device.startswith("cpu") for device in self.observed_devices
        ):
            raise ValueError("fit/serialize certification requires observed CPU devices")
        if self.artifact_manifest is None or self.artifact_manifest_sha256 is None:
            raise ValueError("VERIFIED fit/serialize requires an artifact manifest")
        if manifest_sha256(self.artifact_manifest) != self.artifact_manifest_sha256:
            raise ValueError("fit/serialize artifact manifest SHA-256 mismatch")
        return self


class PredictorReloadResult(BaseModel):
    """Deserialize and predict evidence produced by a new provider process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    outcome: LifecycleOutcome
    fit_process_id: int = Field(ge=1)
    load_process_id: int = Field(ge=1)
    prediction_length: int = Field(ge=1)
    expected_shape: list[int]
    observed_shape: list[int] | None = None
    prediction_values: list[float] = Field(default_factory=list)
    observed_devices: list[str] = Field(default_factory=list)
    artifact_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    runtime_versions: dict[str, str | None] = Field(default_factory=dict)
    checks: dict[str, LifecycleCheckState]
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prediction_values")
    @classmethod
    def validate_prediction_values(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("reload predictions must be finite")
        return values

    @model_validator(mode="after")
    def validate_outcome(self) -> PredictorReloadResult:
        missing = [name for name in RELOAD_REQUIRED_CHECKS if name not in self.checks]
        if missing:
            raise ValueError(f"missing reload checks: {missing}")
        if self.outcome is not LifecycleOutcome.VERIFIED:
            if not self.errors:
                raise ValueError("non-VERIFIED reload results require errors")
            return self
        if self.errors:
            raise ValueError("VERIFIED reload results cannot contain errors")
        if any(
            self.checks[name] is not LifecycleCheckState.PASS
            for name in RELOAD_REQUIRED_CHECKS
        ):
            raise ValueError("VERIFIED reload requires every check to PASS")
        if self.artifact_manifest_sha256 is None:
            raise ValueError("VERIFIED reload requires an artifact manifest SHA-256")
        if self.fit_process_id == self.load_process_id:
            raise ValueError("VERIFIED reload must run in a new process")
        if self.observed_shape != self.expected_shape:
            raise ValueError("reload shape mismatch")
        if len(self.prediction_values) != self.prediction_length:
            raise ValueError("reload prediction length mismatch")
        if not self.observed_devices or any(
            not device.startswith("cpu") for device in self.observed_devices
        ):
            raise ValueError("reload certification requires observed CPU devices")
        return self


class PredictorLifecycleResult(BaseModel):
    """Cross-process aggregate for fit/serialize and reload/predict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lane: Literal["compat", "latest"]
    outcome: LifecycleOutcome
    fit_request_id: str = Field(min_length=1)
    load_request_id: str = Field(min_length=1)
    fit: PredictorFitSerializeResult
    reload: PredictorReloadResult | None = None
    artifact_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> PredictorLifecycleResult:
        if self.fit.lane != self.lane:
            raise ValueError("lifecycle fit lane mismatch")
        if self.reload is not None and self.reload.lane != self.lane:
            raise ValueError("lifecycle reload lane mismatch")
        if self.artifact_manifest_sha256 is not None:
            if self.fit.artifact_manifest_sha256 != self.artifact_manifest_sha256:
                raise ValueError("fit manifest identity mismatch")
            if self.reload is not None and (
                self.reload.artifact_manifest_sha256
                != self.artifact_manifest_sha256
            ):
                raise ValueError("reload manifest identity mismatch")
        if self.outcome is LifecycleOutcome.VERIFIED:
            if self.artifact_manifest_sha256 is None:
                raise ValueError("VERIFIED lifecycle requires an artifact manifest SHA-256")
            if self.errors:
                raise ValueError("VERIFIED lifecycle cannot contain errors")
            if self.fit.outcome is not LifecycleOutcome.VERIFIED:
                raise ValueError("VERIFIED lifecycle requires VERIFIED fit")
            if self.reload is None:
                raise ValueError("VERIFIED lifecycle requires reload evidence")
            if self.reload.outcome is not LifecycleOutcome.VERIFIED:
                raise ValueError("VERIFIED lifecycle requires VERIFIED reload")
            if self.fit.process_id == self.reload.load_process_id:
                raise ValueError("VERIFIED lifecycle requires process restart")
        elif not self.errors:
            raise ValueError("non-VERIFIED lifecycle requires errors")
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


def prediction_sha256(values: list[float]) -> str:
    return sha256_json([float(value) for value in values])


def artifact_tree_sha256(files: list[ArtifactFile]) -> str:
    payload = [
        {
            "relative_path": entry.relative_path,
            "size_bytes": entry.size_bytes,
            "sha256": entry.sha256,
        }
        for entry in sorted(files, key=lambda item: item.relative_path)
    ]
    return sha256_json(payload)


def manifest_sha256(manifest: PredictorArtifactManifest) -> str:
    return sha256_json(manifest.model_dump(mode="json"))


def fit_result_sha256(result: PredictorFitSerializeResult) -> str:
    return sha256_json(result.model_dump(mode="json"))


def reload_result_sha256(result: PredictorReloadResult) -> str:
    return sha256_json(result.model_dump(mode="json"))


def lifecycle_result_sha256(result: PredictorLifecycleResult) -> str:
    return sha256_json(result.model_dump(mode="json"))
