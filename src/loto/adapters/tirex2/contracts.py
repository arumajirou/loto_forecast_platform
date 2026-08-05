from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ID = "NX-AI/TiRex-2"
REVISION = "05e5b26db52bfb256f1ae1bdf785589850482de3"
QUANTILE_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
SUPPORTED_HORIZONS = (1, 2, 5)


class SeriesLayout(StrEnum):
    POSITION_LOCAL = "position_local"
    POSITION_BATCH_INDEPENDENT = "position_batch_independent"
    POSITION_JOINT_MULTIVARIATE = "position_joint_multivariate"


class ExecutionMode(StrEnum):
    BATCH_RECOMPUTE = "batch_recompute"


class GameGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    position_count: int = Field(ge=1)
    candidate_min: int
    candidate_max: int
    strictly_increasing: bool = True

    @model_validator(mode="after")
    def validate_bounds(self) -> GameGeometry:
        if self.candidate_min > self.candidate_max:
            raise ValueError("candidate_min must be <= candidate_max")
        if self.strictly_increasing:
            capacity = self.candidate_max - self.candidate_min + 1
            if self.position_count > capacity:
                raise ValueError("position_count exceeds the candidate range capacity")
        return self


class CovariateBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    names: list[str]
    values: list[list[float]]
    source_timestamps: list[datetime] = Field(default_factory=list)
    known_at_prediction_time: bool
    future_actual_dependency: bool = False

    @model_validator(mode="after")
    def validate_matrix(self) -> CovariateBlock:
        if len(self.names) != len(self.values):
            raise ValueError("covariate names and value rows must have equal length")
        if len(set(self.names)) != len(self.names):
            raise ValueError("covariate names must be unique")
        widths = {len(row) for row in self.values}
        if len(widths) > 1:
            raise ValueError("all covariate rows must have the same length")
        if any(not isfinite(value) for row in self.values for value in row):
            raise ValueError("covariates must contain only finite values")
        return self


class Tirex2Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    run_id: str = Field(min_length=1)
    operation: Literal["predict"] = "predict"
    model_id: Literal["tirex-2"] = "tirex-2"
    repo_id: Literal[REPO_ID] = REPO_ID
    revision: Literal[REVISION] = REVISION
    game_geometry: GameGeometry
    series_layout: SeriesLayout
    target_columns: list[str]
    target_history: list[list[float]]
    past_covariates: CovariateBlock | None = None
    future_covariates: CovariateBlock | None = None
    prediction_issue_time: datetime
    context_length: int = Field(ge=1, le=2048)
    prediction_length: Literal[1, 2, 5]
    quantile_levels: Annotated[list[float], Field(min_length=9, max_length=9)] = Field(
        default_factory=lambda: list(QUANTILE_LEVELS)
    )
    point_method: Literal["native_q0.5"] = "native_q0.5"
    execution_mode: Literal["batch_recompute"] = "batch_recompute"
    device: Literal["cpu", "cuda"] = "cpu"
    dtype: Literal["float32"] = "float32"
    seed: int = 1
    local_files_only: Literal[True] = True
    snapshot_path: str | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> Tirex2Request:
        target_count = len(self.target_columns)
        if target_count != self.game_geometry.position_count:
            raise ValueError("target_columns must match game_geometry.position_count")
        if len(set(self.target_columns)) != target_count:
            raise ValueError("target_columns must be unique")
        if len(self.target_history) != target_count:
            raise ValueError("target_history row count must match target_columns")
        if any(len(row) != self.context_length for row in self.target_history):
            raise ValueError("each target_history row must equal context_length")
        if any(not isfinite(value) for row in self.target_history for value in row):
            raise ValueError("target_history must contain only finite values")
        if tuple(self.quantile_levels) != QUANTILE_LEVELS:
            raise ValueError("quantile_levels must be exactly q0.1 through q0.9")
        if self.series_layout == SeriesLayout.POSITION_LOCAL and target_count != 1:
            raise ValueError("position_local requires exactly one target")
        self._validate_covariates()
        return self

    def _validate_covariates(self) -> None:
        if self.past_covariates is not None:
            widths = {len(row) for row in self.past_covariates.values}
            if widths and widths != {self.context_length}:
                raise ValueError("past covariates must have context_length values")
        if self.future_covariates is None:
            return
        widths = {len(row) for row in self.future_covariates.values}
        if widths and widths != {self.prediction_length}:
            raise ValueError("future covariates must have prediction_length values")
        if not self.future_covariates.known_at_prediction_time:
            raise ValueError("future covariates must be known at prediction time")
        if self.future_covariates.future_actual_dependency:
            raise ValueError("future covariates may not depend on future actuals")
        if any(
            timestamp > self.prediction_issue_time
            for timestamp in self.future_covariates.source_timestamps
        ):
            raise ValueError("future covariate source timestamps exceed prediction_issue_time")


class ModelIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: Literal["tirex-2"] = "tirex-2"
    repo_id: Literal[REPO_ID] = REPO_ID
    revision: Literal[REVISION] = REVISION
    package: Literal["tirex-2"] = "tirex-2"
    package_version: Literal["0.1.1"] = "0.1.1"
    weight_sha256: str
    config_sha256: str


class RuntimeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_pid: int
    requested_device: Literal["cpu", "cuda"]
    effective_device: Literal["cpu", "cuda"]
    model_parameter_device: str | None
    target_tensor_device: str
    past_covariate_device: str | None
    future_covariate_device: str | None
    output_tensor_device: str | None
    dtype: Literal["float32"]
    autocast_dtype: str | None = None
    cpu_fallback: bool
    load_time_seconds: float = Field(ge=0)
    inference_time_seconds: float = Field(ge=0)


class GpuEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gpu_uuid: str | None = None
    external_pid_match: bool | None = None
    vram_before_bytes: int = Field(ge=0)
    vram_peak_bytes: int = Field(ge=0)
    vram_after_bytes: int = Field(ge=0)


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_path: str
    local_files_only: Literal[True] = True
    reference_manifest_saved: bool = False
    base_snapshot_reloaded: bool = False
    prediction_reproduced: bool = False


class Tirex2Response(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    status: Literal["OK"] = "OK"
    run_id: str
    model_identity: ModelIdentity
    effective_arguments: dict[str, object]
    point_forecast: list[list[float]]
    point_method: Literal["native_q0.5"] = "native_q0.5"
    quantiles: dict[str, list[list[float]]]
    samples: None = None
    series_identity: list[str]
    prediction_index: list[int]
    runtime_evidence: RuntimeEvidence
    gpu_evidence: GpuEvidence
    artifact_reference: ArtifactReference
    pretraining_overlap: Literal["UNKNOWN"] = "UNKNOWN"
    warnings: list[str] = Field(default_factory=list)
    unsupported_arguments: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_output(self) -> Tirex2Response:
        target_count = len(self.series_identity)
        horizon = len(self.prediction_index)
        if any(len(row) != horizon for row in self.point_forecast):
            raise ValueError("point_forecast rows must match prediction_index")
        if len(self.point_forecast) != target_count:
            raise ValueError("point_forecast target count must match series_identity")
        expected_keys = [f"{level:.1f}" for level in QUANTILE_LEVELS]
        if list(self.quantiles) != expected_keys:
            raise ValueError("quantile keys must be ordered q0.1 through q0.9")
        matrices = [self.quantiles[key] for key in expected_keys]
        for matrix in matrices:
            if len(matrix) != target_count or any(len(row) != horizon for row in matrix):
                raise ValueError("quantile matrix shape mismatch")
            if any(not isfinite(value) for row in matrix for value in row):
                raise ValueError("quantiles must contain only finite values")
        for target_index in range(target_count):
            for horizon_index in range(horizon):
                values = [matrix[target_index][horizon_index] for matrix in matrices]
                if values != sorted(values):
                    raise ValueError("quantile crossing detected")
        if self.point_forecast != self.quantiles["0.5"]:
            raise ValueError("point_forecast must equal native q0.5")
        if (
            self.runtime_evidence.requested_device == "cuda"
            and self.runtime_evidence.effective_device != "cuda"
        ):
            raise ValueError("CUDA request may not silently fall back to CPU")
        if self.runtime_evidence.cpu_fallback:
            raise ValueError("cpu_fallback must be false for successful responses")
        return self
