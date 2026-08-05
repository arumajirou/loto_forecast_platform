from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AUTO_MODEL_NAMES = (
    "AutoLightGBM",
    "AutoXGBoost",
    "AutoCatboost",
    "AutoLinearRegression",
    "AutoRidge",
    "AutoLasso",
    "AutoElasticNet",
    "AutoRandomForest",
)

CORE_MODEL_NAMES = (
    "linear_regression",
    "ridge",
    "lasso",
    "elastic_net",
    "random_forest",
    "lightgbm",
    "xgboost",
    "catboost",
)


class RunMode(StrEnum):
    CORE = "core"
    AUTO = "auto"


class SearchParameter(BaseModel):
    """Declarative Optuna search parameter used by AutoMLForecast models."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["int", "float", "categorical"]
    low: int | float | None = None
    high: int | float | None = None
    choices: list[Any] | None = None
    log: bool = False
    step: int | float | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> SearchParameter:
        if self.kind == "categorical":
            if not self.choices:
                raise ValueError("categorical search parameters require non-empty choices")
            if self.low is not None or self.high is not None:
                raise ValueError("categorical search parameters cannot define low/high")
            return self
        if self.low is None or self.high is None:
            raise ValueError(f"{self.kind} search parameters require low and high")
        if self.low >= self.high:
            raise ValueError("search parameter low must be smaller than high")
        if self.choices is not None:
            raise ValueError(f"{self.kind} search parameters cannot define choices")
        return self


class LagTransformSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "rolling_mean",
        "rolling_std",
        "rolling_min",
        "rolling_max",
        "expanding_mean",
        "exponentially_weighted_mean",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class TargetTransformSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["differences", "local_standard_scaler"]
    params: dict[str, Any] = Field(default_factory=dict)


class PredictionIntervalsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_windows: int = Field(default=4, ge=2)
    h: int = Field(default=1, ge=1)
    method: Literal["conformal_distribution", "conformal_error"] = "conformal_distribution"
    levels: list[float] = Field(default_factory=lambda: [80.0, 90.0])

    @field_validator("levels")
    @classmethod
    def validate_levels(cls, values: list[float]) -> list[float]:
        if not values:
            raise ValueError("prediction interval levels cannot be empty")
        normalized = sorted({float(value) for value in values})
        if any(value <= 0 or value >= 100 for value in normalized):
            raise ValueError("prediction interval levels must be between 0 and 100")
        return normalized


class CoreConfig(BaseModel):
    """Arguments mapped to MLForecast constructor, fit, predict and CV APIs."""

    model_config = ConfigDict(extra="forbid")

    models: list[str] = Field(default_factory=lambda: ["ridge"])
    model_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    freq: int | str = 1
    lags: list[int] | None = Field(default_factory=lambda: [1, 2, 3, 5, 10, 20])
    lag_transforms: dict[int, list[LagTransformSpec]] = Field(default_factory=dict)
    date_features: list[str] = Field(default_factory=list)
    num_threads: int = Field(default=1, ge=1)
    target_transforms: list[TargetTransformSpec] = Field(default_factory=list)
    date_features_as_dummies: bool = False
    drop_auxiliary_columns: bool = True

    static_features: list[str] | None = None
    dropna: bool = True
    keep_last_n: int | None = Field(default=None, ge=1)
    max_horizon: int | None = Field(default=None, ge=1)
    horizons: list[int] | None = None
    fitted: bool = False
    as_numpy: bool = False
    weight_col: str | None = None
    validate_data: bool = True
    cache_train_df: bool = True
    prediction_intervals: PredictionIntervalsConfig | None = None

    cv_n_windows: int = Field(default=3, ge=1)
    cv_step_size: int | None = Field(default=None, ge=1)
    cv_refit: bool | int = True
    cv_input_size: int | None = Field(default=None, ge=1)

    @field_validator("models")
    @classmethod
    def validate_models(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("at least one core model is required")
        unknown = sorted(set(values) - set(CORE_MODEL_NAMES))
        if unknown:
            raise ValueError(f"unsupported core models: {unknown}")
        if len(values) != len(set(values)):
            raise ValueError("core model names must be unique")
        return values

    @field_validator("lags")
    @classmethod
    def validate_lags(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        normalized = sorted({int(value) for value in values})
        if not normalized or normalized[0] < 1:
            raise ValueError("lags must contain positive integers")
        return normalized

    @field_validator("horizons")
    @classmethod
    def validate_horizons(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        normalized = sorted({int(value) for value in values})
        if not normalized or normalized[0] < 1:
            raise ValueError("horizons must contain positive integers")
        return normalized


class AutoConfig(BaseModel):
    """Arguments mapped to AutoMLForecast constructor and fit APIs."""

    model_config = ConfigDict(extra="forbid")

    models: list[str] = Field(default_factory=lambda: ["AutoRidge"])
    search_spaces: dict[str, dict[str, SearchParameter]] = Field(default_factory=dict)
    freq: int | str = 1
    season_length: int = Field(default=1, ge=1)
    num_threads: int = Field(default=1, ge=1)
    reuse_cv_splits: bool = True

    n_windows: int = Field(default=3, ge=1)
    num_samples: int = Field(default=20, ge=1)
    step_size: int | None = Field(default=None, ge=1)
    input_size: int | None = Field(default=None, ge=1)
    refit: bool | int = False
    fitted: bool = False
    weight_col: str | None = None
    prediction_intervals: PredictionIntervalsConfig | None = None

    sampler: Literal["tpe", "random", "qmc", "cmaes"] = "tpe"
    timeout_seconds: float | None = Field(default=None, gt=0)
    n_jobs: int = Field(default=1, ge=1)

    @field_validator("models")
    @classmethod
    def validate_models(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("at least one AutoMLForecast model is required")
        unknown = sorted(set(values) - set(AUTO_MODEL_NAMES))
        if unknown:
            raise ValueError(f"unsupported AutoMLForecast models: {unknown}")
        if len(values) != len(set(values)):
            raise ValueError("AutoMLForecast model names must be unique")
        return values

    @model_validator(mode="after")
    def validate_search_spaces(self) -> AutoConfig:
        unknown = sorted(set(self.search_spaces) - set(self.models))
        if unknown:
            raise ValueError(f"search spaces reference unselected models: {unknown}")
        return self


class MLForecastRunConfig(BaseModel):
    """Leakage-safe execution contract for MLForecast and AutoMLForecast."""

    model_config = ConfigDict(extra="forbid")

    mode: RunMode = RunMode.CORE
    id_col: str = "unique_id"
    time_col: str = "ds"
    target_col: str = "y"
    h: int = Field(default=1, ge=1)
    holdout_size: int = Field(default=1, ge=1)
    prospective_h: int = Field(default=1, ge=1)
    seed: int = 1
    fixed_baseline_value: float | None = None
    artifact_root: Path = Path("artifacts/mlforecast")
    save_model: bool = True
    verify_save_load: bool = True
    core: CoreConfig = Field(default_factory=CoreConfig)
    auto: AutoConfig = Field(default_factory=AutoConfig)

    @model_validator(mode="after")
    def validate_horizon_contract(self) -> MLForecastRunConfig:
        if self.h != self.holdout_size:
            raise ValueError("h must equal holdout_size for an exact holdout comparison")
        return self
