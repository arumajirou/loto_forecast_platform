from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BASE_MODEL_ID = "timesfm-2.5-200m"
QUANTILE_KEYS = tuple(f"0.{index}" for index in range(1, 10))
FORMAL_HORIZONS = (1, 2, 5)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class Backend(StrEnum):
    PYTORCH_NATIVE = "pytorch_native"
    PYTORCH_SOURCE = "pytorch_source"
    TRANSFORMERS = "transformers"
    XREG = "xreg"


class GameGeometry(StrictModel):
    game_id: str = Field(min_length=1)
    position_count: int = Field(ge=1, le=64)
    candidate_min: int
    candidate_max: int
    strictly_increasing: bool = False

    @model_validator(mode="after")
    def validate_candidate_space(self) -> GameGeometry:
        if self.candidate_min > self.candidate_max:
            raise ValueError("candidate_min must be <= candidate_max")
        if self.strictly_increasing:
            capacity = self.candidate_max - self.candidate_min + 1
            if capacity < self.position_count:
                raise ValueError("candidate range cannot hold all strictly increasing positions")
        return self


class ForecastConfigLedger(StrictModel):
    normalize_inputs: bool = True
    use_continuous_quantile_head: bool = True
    force_flip_invariance: bool = True
    infer_is_positive: bool = True
    fix_quantile_crossing: bool = True
    return_backcast: bool = False
    per_core_batch_size: int = Field(default=1, ge=1, le=4096)
    torch_compile: bool = False
    max_horizon: int = Field(default=1024, ge=1, le=1024)


class TimesFM25Request(StrictModel):
    schema_version: Literal[2] = 2
    run_id: str = Field(min_length=1)
    operation: Literal["predict", "reload_predict"] = "predict"
    base_model_id: Literal[BASE_MODEL_ID] = BASE_MODEL_ID
    backend: Backend
    repo_id: str = Field(min_length=1)
    revision: str = Field(min_length=7)
    game_geometry: GameGeometry
    series_layout: Literal["batched_univariate"] = "batched_univariate"
    series_ids: list[str] = Field(min_length=1)
    history: dict[str, list[float]]
    context_length: int = Field(ge=1, le=16384)
    prediction_length: int = Field(ge=1, le=1024)
    forecast_config: ForecastConfigLedger = Field(default_factory=ForecastConfigLedger)
    device: Literal["cpu", "cuda"] = "cpu"
    dtype: Literal["float32"] = "float32"
    seed: int = 1
    local_files_only: Literal[True] = True
    snapshot_path: str | None = None

    @model_validator(mode="after")
    def validate_series_contract(self) -> TimesFM25Request:
        if len(self.series_ids) != self.game_geometry.position_count:
            raise ValueError("series_ids length must equal game_geometry.position_count")
        if len(set(self.series_ids)) != len(self.series_ids):
            raise ValueError("series_ids must be unique")
        if set(self.history) != set(self.series_ids):
            raise ValueError("history keys must exactly match series_ids")
        lengths = {len(self.history[series_id]) for series_id in self.series_ids}
        if len(lengths) != 1:
            raise ValueError("all history series must have equal length")
        history_length = next(iter(lengths))
        if history_length < self.context_length:
            raise ValueError("history length must be >= context_length")
        if self.prediction_length > self.forecast_config.max_horizon:
            raise ValueError("prediction_length exceeds forecast_config.max_horizon")
        if not self.forecast_config.use_continuous_quantile_head:
            raise ValueError("contract v2 requires the continuous quantile head")
        for series_id in self.series_ids:
            if not all(math.isfinite(float(value)) for value in self.history[series_id]):
                raise ValueError(f"history contains NaN or Inf: {series_id}")
        return self


class ModelIdentity(StrictModel):
    base_model_id: Literal[BASE_MODEL_ID] = BASE_MODEL_ID
    backend: Backend
    checkpoint_repo_id: str
    checkpoint_revision: str
    package_version: str
    source_revision: str | None = None
    weight_sha256: str | None = None
    algorithm_identity: Literal[BASE_MODEL_ID] = BASE_MODEL_ID


class RuntimeEvidence(StrictModel):
    provider_pid: int = Field(ge=1)
    model_parameter_device: str
    input_device: str
    mean_output_device: str
    quantile_output_device: str
    cpu_fallback: bool
    load_time_seconds: float = Field(ge=0)
    compile_time_seconds: float = Field(ge=0)
    inference_time_seconds: float = Field(ge=0)
    compile_requested: bool
    compile_effective: bool
    compile_backend: str | None = None
    graph_break_count: int | None = Field(default=None, ge=0)


class GPUExecutionEvidence(StrictModel):
    requested: bool
    cuda_available: bool
    gpu_used: bool
    provider_pid: int = Field(ge=1)
    external_pid_match: bool
    gpu_uuid: str | None = None
    vram_before_bytes: int = Field(ge=0)
    vram_peak_bytes: int = Field(ge=0)
    vram_after_bytes: int = Field(ge=0)
    cpu_fallback: bool
    certification_status: Literal["NOT_REQUESTED", "PARTIAL", "PASS", "FAIL"]
    failure_reason: str | None = None


class ArtifactReference(StrictModel):
    repo_id: str
    revision: str
    snapshot_path: str
    config_sha256: str | None = None
    weight_sha256: dict[str, str] = Field(default_factory=dict)
    reference_manifest_saved: bool = False
    snapshot_reloaded: bool = False


Matrix = list[list[float]]


class TimesFM25Response(StrictModel):
    status: Literal["OK"] = "OK"
    schema_version: Literal[2] = 2
    provider_version: Literal[2] = 2
    model_identity: ModelIdentity
    effective_arguments: dict[str, Any]
    median_forecast: Matrix
    mean_forecast: Matrix
    quantiles: dict[str, Matrix]
    series_identity: list[str]
    prediction_index: list[int]
    backcast: Matrix | None = None
    runtime_evidence: RuntimeEvidence
    gpu_evidence: GPUExecutionEvidence
    artifact_reference: ArtifactReference
    warnings: list[str] = Field(default_factory=list)
    unsupported_arguments: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_forecast_contract(self) -> TimesFM25Response:
        series_count = len(self.series_identity)
        horizon = len(self.prediction_index)
        if horizon < 1:
            raise ValueError("prediction_index must be non-empty")
        if self.prediction_index != list(range(horizon)):
            raise ValueError("prediction_index must be zero-based and contiguous")
        matrices = (
            ("median_forecast", self.median_forecast),
            ("mean_forecast", self.mean_forecast),
        )
        for name, matrix in matrices:
            _validate_matrix(name, matrix, series_count, horizon)
        if set(self.quantiles) != set(QUANTILE_KEYS):
            raise ValueError("quantiles must contain q0.1 through q0.9 exactly")
        for key in QUANTILE_KEYS:
            _validate_matrix(f"quantiles[{key}]", self.quantiles[key], series_count, horizon)
        for series_index in range(series_count):
            for step in range(horizon):
                values = [self.quantiles[key][series_index][step] for key in QUANTILE_KEYS]
                if any(left > right for left, right in zip(values, values[1:], strict=False)):
                    raise ValueError("quantile crossing detected")
                if not math.isclose(
                    self.median_forecast[series_index][step],
                    self.quantiles["0.5"][series_index][step],
                    rel_tol=1e-5,
                    abs_tol=1e-5,
                ):
                    raise ValueError("native point forecast must equal q0.5")
        if self.unsupported_arguments:
            raise ValueError("successful response cannot contain unsupported_arguments")
        return self


def _validate_matrix(name: str, matrix: Matrix, rows: int, columns: int) -> None:
    if len(matrix) != rows:
        raise ValueError(f"{name} row count mismatch")
    for row in matrix:
        if len(row) != columns:
            raise ValueError(f"{name} horizon mismatch")
        if not all(math.isfinite(float(value)) for value in row):
            raise ValueError(f"{name} contains NaN or Inf")


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
