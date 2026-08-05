from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArgumentStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_BY_VERSION = "UNSUPPORTED_BY_VERSION"
    REJECTED = "REJECTED"


class FailureClass(StrEnum):
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    IMPORT_FAILED = "IMPORT_FAILED"
    INVALID_REQUEST = "INVALID_REQUEST"
    ARGUMENT_REJECTED = "ARGUMENT_REJECTED"
    FIT_FAILED = "FIT_FAILED"
    PREDICT_FAILED = "PREDICT_FAILED"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    EVALUATION_FAILED = "EVALUATION_FAILED"
    ARTIFACT_FAILED = "ARTIFACT_FAILED"
    TIMEOUT = "TIMEOUT"


class SeriesLayout(StrEnum):
    POSITION_LOCAL = "position_local"
    POSITION_MULTIVARIATE = "position_multivariate"
    POSITION_GLOBAL_SEQUENCE = "position_global_sequence"
    CANDIDATE_BINARY = "candidate_binary"
    POSITION_DIGIT = "position_digit"


class RuntimeKind(StrEnum):
    NOTORCH = "notorch"
    TORCH = "torch"


class DevicePolicy(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"
    AUTO = "auto"


class GameGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    positions: int = Field(ge=1, le=20)
    min_value: int
    max_value: int
    draw_no_col: str = "draw_no"
    time_col: str = "draw_date"
    position_prefix: str = "n"

    @model_validator(mode="after")
    def validate_range(self) -> GameGeometry:
        if self.min_value > self.max_value:
            raise ValueError("min_value must be <= max_value")
        return self

    @property
    def position_columns(self) -> list[str]:
        return [f"{self.position_prefix}{index}" for index in range(1, self.positions + 1)]


class ModelIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    public_name: str = Field(min_length=1)
    module: str = "darts.models"
    class_name: str | None = None
    wrapper_name: str | None = None
    base_models: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_wrapper(self) -> ModelIdentity:
        if self.wrapper_name and not self.base_models:
            raise ValueError("wrapper_name requires at least one base model")
        return self


class ArgumentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    argument: str
    status: ArgumentStatus
    reason: str
    value_repr: str


BaselineName = Literal[
    "random",
    "fixed",
    "mean",
    "median",
    "last",
    "frequency",
    "seasonal_naive",
]


class EvaluationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    holdout_size: int = Field(default=1, ge=1, le=512)
    tolerance: float = Field(default=1.0, ge=0.0)
    season_length: int = Field(default=1, ge=1)
    fixed_value: float | None = None
    baselines: tuple[BaselineName, ...] = (
        "random",
        "fixed",
        "mean",
        "median",
        "last",
        "frequency",
        "seasonal_naive",
    )


class PersistencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    save_model: bool = False
    verify_save_load: bool = False
    rtol: float = Field(default=1e-8, ge=0.0)
    atol: float = Field(default=1e-8, ge=0.0)

    @model_validator(mode="after")
    def validate_save_contract(self) -> PersistencePolicy:
        if self.verify_save_load and not self.save_model:
            raise ValueError("verify_save_load requires save_model=true")
        return self


class ProspectivePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seal_predictions: bool = False
    actual_known: Literal[False] = False


class DartsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    mode: Literal["discover", "fit_predict"]
    geometry: GameGeometry
    model: ModelIdentity | None = None
    series_layout: SeriesLayout = SeriesLayout.POSITION_LOCAL
    horizon: int = Field(default=1, ge=1, le=512)
    model_args: dict[str, Any] = Field(default_factory=dict)
    base_model_args: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fit_args: dict[str, Any] = Field(default_factory=dict)
    predict_args: dict[str, Any] = Field(default_factory=dict)
    runtime: RuntimeKind = RuntimeKind.NOTORCH
    device: DevicePolicy = DevicePolicy.CPU
    seed: int = 1
    timeout_seconds: int = Field(default=900, ge=1, le=86400)
    artifact_dir: Path
    evaluation: EvaluationPolicy = Field(default_factory=EvaluationPolicy)
    persistence: PersistencePolicy = Field(default_factory=PersistencePolicy)
    prospective: ProspectivePolicy = Field(default_factory=ProspectivePolicy)

    @model_validator(mode="after")
    def validate_mode_contract(self) -> DartsRequest:
        if self.mode == "fit_predict" and self.model is None:
            raise ValueError("fit_predict requires model identity")
        if self.mode == "discover" and self.model is not None:
            raise ValueError("discover must not include a model identity")
        if self.runtime == RuntimeKind.NOTORCH and self.device != DevicePolicy.CPU:
            raise ValueError("notorch runtime only supports device=cpu")
        if self.evaluation.enabled and self.horizon != self.evaluation.holdout_size:
            raise ValueError("evaluation requires horizon == holdout_size")
        if self.evaluation.enabled and self.prospective.seal_predictions:
            raise ValueError("evaluation and prospective sealing are mutually exclusive")
        return self


class DartsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str
    status: Literal["SUCCEEDED", "PARTIAL", "FAILED"]
    failure_class: FailureClass | None = None
    message: str | None = None
    predictions: list[list[float]] | None = None
    model_inventory: list[dict[str, Any]] | None = None
    argument_ledger: list[ArgumentDecision] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None
    baseline_metrics: dict[str, dict[str, Any]] | None = None
    runtime_certification: list[dict[str, Any]] | None = None
    prospective_seal: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
