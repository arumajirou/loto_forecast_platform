from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProviderOperation(StrEnum):
    DISCOVER = "discover"
    FIT_PREDICT_SAVE = "fit_predict_save"
    LOAD_PREDICT = "load_predict"
    EVALUATE = "evaluate"
    LEADERBOARD = "leaderboard"
    BACKTEST = "backtest"
    RUNTIME_CERTIFY = "runtime_certify"


class ExecutionMode(StrEnum):
    PRESET_AUTOML = "preset_automl"
    EXPLICIT_SINGLE_MODEL = "explicit_single_model"
    EXPLICIT_MULTI_MODEL = "explicit_multi_model"
    HPO_SINGLE_MODEL = "hpo_single_model"
    ZERO_SHOT_FOUNDATION = "zero_shot_foundation"
    FINE_TUNE_FOUNDATION = "fine_tune_foundation"


class DeviceRequest(StrEnum):
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


class ArgumentStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    TRANSFORMED = "TRANSFORMED"
    SUPPORTED_WITH_CONDITION = "SUPPORTED_WITH_CONDITION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_BY_VERSION = "UNSUPPORTED_BY_VERSION"
    REJECTED = "REJECTED"
    DROPPED_WITH_REASON = "DROPPED_WITH_REASON"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TimelinePolicy(StrictModel):
    mode: Literal["synthetic_regular"] = "synthetic_regular"
    frequency: Literal["D"] = "D"
    base_timestamp: datetime = Field(
        default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    source_order_field: str = "draw_no"
    source_timestamp_field: str = "draw_date"

    @field_validator("base_timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("base_timestamp must be timezone-aware")
        return value


class GameGeometry(StrictModel):
    game_id: str = Field(min_length=1)
    position_columns: tuple[str, ...] = Field(min_length=1)
    candidate_min: int
    candidate_max: int
    selection_count: int = Field(gt=0)
    horizon: int = Field(default=1, gt=0)
    allow_duplicates: bool = False
    sort_policy: Literal["preserve", "ascending"] = "ascending"
    timeline: TimelinePolicy = Field(default_factory=TimelinePolicy)

    @field_validator("position_columns")
    @classmethod
    def validate_position_columns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("position_columns must be unique")
        for column in value:
            if not column or not column.replace("_", "a").isalnum() or column[0].isdigit():
                raise ValueError(f"invalid position column: {column!r}")
        return value

    @model_validator(mode="after")
    def validate_candidate_domain(self) -> GameGeometry:
        if self.candidate_max < self.candidate_min:
            raise ValueError("candidate_max must be >= candidate_min")
        domain_size = self.candidate_max - self.candidate_min + 1
        if self.selection_count > domain_size and not self.allow_duplicates:
            raise ValueError("selection_count exceeds candidate domain without duplicates")
        if self.selection_count != len(self.position_columns):
            raise ValueError("selection_count must equal the number of position_columns")
        return self


class PredictorConfig(StrictModel):
    target: str = "target"
    known_covariates_names: tuple[str, ...] = ()
    prediction_length: int = Field(default=1, gt=0)
    freq: str = "D"
    eval_metric: str = "MAE"
    eval_metric_seasonal_period: int | None = Field(default=None, gt=0)
    horizon_weight: tuple[float, ...] | None = None
    quantile_levels: tuple[float, ...] = (0.1, 0.5, 0.9)
    cache_predictions: bool = True

    @field_validator("quantile_levels")
    @classmethod
    def validate_quantiles(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(set(value)) != len(value):
            raise ValueError("quantile_levels must be unique")
        if any(level <= 0.0 or level >= 1.0 for level in value):
            raise ValueError("quantile_levels must be strictly between 0 and 1")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_horizon_weight(self) -> PredictorConfig:
        if self.horizon_weight is not None:
            if len(self.horizon_weight) != self.prediction_length:
                raise ValueError("horizon_weight length must equal prediction_length")
            if any(weight < 0 for weight in self.horizon_weight):
                raise ValueError("horizon_weight values must be non-negative")
            if sum(self.horizon_weight) <= 0:
                raise ValueError("horizon_weight must contain a positive value")
        return self


class FitConfig(StrictModel):
    time_limit_seconds: int | None = Field(default=None, gt=0)
    presets: str | None = "fast_training"
    hyperparameters: dict[str, Any] | str | None = None
    hyperparameter_tune_kwargs: dict[str, Any] | str | None = None
    excluded_model_types: tuple[str, ...] = ()
    ensemble_hyperparameters: dict[str, Any] | tuple[dict[str, Any], ...] | None = None
    num_val_windows: int | tuple[int, ...] | Literal["auto"] = 1
    val_step_size: int | None = Field(default=None, gt=0)
    refit_every_n_windows: int | Literal["auto"] | None = 1
    refit_full: bool = False
    enable_ensemble: bool = True
    skip_model_selection: bool = False

    @field_validator("num_val_windows")
    @classmethod
    def validate_num_val_windows(
        cls, value: int | tuple[int, ...] | Literal["auto"]
    ) -> int | tuple[int, ...] | Literal["auto"]:
        if value == "auto":
            return value
        values = (value,) if isinstance(value, int) else value
        if not values or any(window <= 0 for window in values):
            raise ValueError("num_val_windows must contain positive integers")
        return value


class CovariatePayload(StrictModel):
    past_covariates_names: tuple[str, ...] = ()
    static_feature_names: tuple[str, ...] = ()
    future_known_covariates: tuple[dict[str, Any], ...] = ()


class ProviderRequestV2(StrictModel):
    schema_version: Literal[2] = 2
    provider_version: Literal[2] = 2
    run_id: str = Field(min_length=1)
    operation: ProviderOperation
    execution_mode: ExecutionMode = ExecutionMode.PRESET_AUTOML
    model_ids: tuple[str, ...] = ()
    artifact_dir: str | None = None
    history: tuple[dict[str, Any], ...] = ()
    geometry: GameGeometry | None = None
    predictor: PredictorConfig = Field(default_factory=PredictorConfig)
    fit: FitConfig = Field(default_factory=FitConfig)
    covariates: CovariatePayload = Field(default_factory=CovariatePayload)
    seed: int = 1
    requested_device: DeviceRequest = DeviceRequest.AUTO

    @model_validator(mode="after")
    def validate_operation_contract(self) -> ProviderRequestV2:
        needs_history = self.operation in {
            ProviderOperation.FIT_PREDICT_SAVE,
            ProviderOperation.LOAD_PREDICT,
            ProviderOperation.EVALUATE,
            ProviderOperation.BACKTEST,
            ProviderOperation.RUNTIME_CERTIFY,
        }
        if needs_history and not self.history:
            raise ValueError(f"{self.operation.value} requires non-empty history")
        if needs_history and self.geometry is None:
            raise ValueError(f"{self.operation.value} requires geometry")
        if self.operation in {
            ProviderOperation.FIT_PREDICT_SAVE,
            ProviderOperation.LOAD_PREDICT,
            ProviderOperation.RUNTIME_CERTIFY,
        } and not self.artifact_dir:
            raise ValueError(f"{self.operation.value} requires artifact_dir")

        if self.execution_mode in {
            ExecutionMode.EXPLICIT_SINGLE_MODEL,
            ExecutionMode.HPO_SINGLE_MODEL,
            ExecutionMode.ZERO_SHOT_FOUNDATION,
            ExecutionMode.FINE_TUNE_FOUNDATION,
        } and len(self.model_ids) != 1:
            raise ValueError(f"{self.execution_mode.value} requires exactly one model_id")
        if self.execution_mode is ExecutionMode.EXPLICIT_MULTI_MODEL and len(self.model_ids) < 2:
            raise ValueError("explicit_multi_model requires at least two model_ids")
        if self.execution_mode is ExecutionMode.PRESET_AUTOML and self.model_ids:
            raise ValueError("preset_automl must not silently accept explicit model_ids")

        if self.geometry is not None:
            if self.predictor.prediction_length != self.geometry.horizon:
                raise ValueError("predictor.prediction_length must equal geometry.horizon")
        return self


class ArgumentLedgerEntry(StrictModel):
    argument: str
    requested_value: Any = None
    effective_value: Any = None
    status: ArgumentStatus
    reason: str | None = None


class PredictionRecord(StrictModel):
    item_id: str
    timestamp: datetime
    horizon_step: int = Field(gt=0)
    mean: float
    quantiles: dict[str, float] = Field(default_factory=dict)


class RuntimeEvidence(StrictModel):
    requested_device: DeviceRequest
    resolved_device: Literal["cpu", "cuda", "unknown"] = "unknown"
    cuda_available: bool | None = None
    gpu_used: bool = False
    cpu_fallback: bool = False
    pid: int | None = None
    vram_before_bytes: int | None = Field(default=None, ge=0)
    vram_peak_bytes: int | None = Field(default=None, ge=0)
    vram_after_bytes: int | None = Field(default=None, ge=0)
    evidence_status: Literal["NOT_RUN", "PARTIAL", "CERTIFIED", "FAILED"] = "NOT_RUN"


class ProviderError(StrictModel):
    code: str
    phase: str
    message: str
    error_type: str | None = None


class ProviderResponseV2(StrictModel):
    schema_version: Literal[2] = 2
    provider_version: Literal[2] = 2
    run_id: str
    status: Literal["OK", "ERROR", "PARTIAL"]
    operation: ProviderOperation
    predictions: tuple[PredictionRecord, ...] = ()
    model_inventory: tuple[dict[str, Any], ...] = ()
    ensemble_inventory: tuple[dict[str, Any], ...] = ()
    argument_ledger: tuple[ArgumentLedgerEntry, ...] = ()
    artifacts: dict[str, str] = Field(default_factory=dict)
    runtime_evidence: RuntimeEvidence | None = None
    error: ProviderError | None = None

    @model_validator(mode="after")
    def validate_status(self) -> ProviderResponseV2:
        if self.status == "ERROR" and self.error is None:
            raise ValueError("ERROR response requires error payload")
        if self.status == "OK" and self.error is not None:
            raise ValueError("OK response must not include error payload")
        return self
