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
        if self.log and self.step is not None:
            raise ValueError("logarithmic search parameters cannot define step")
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
    """Arguments mapped to the frozen MLForecast 1.1.0 APIs."""

    model_config = ConfigDict(extra="forbid")

    models: list[str] = Field(default_factory=lambda: ["ridge"])
    model_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    models_fit_kwargs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    freq: int | str = 1
    lags: list[int] | None = Field(default_factory=lambda: [1, 2, 3, 5, 10, 20])
    lag_transforms: dict[int, list[LagTransformSpec]] = Field(default_factory=dict)
    date_features: list[str] = Field(default_factory=list)
    num_threads: int = Field(default=1, ge=1)
    target_transforms: list[TargetTransformSpec] = Field(default_factory=list)
    date_features_as_dummies: bool = False
    drop_auxiliary_columns: bool | list[str] = True

    dropna: bool = True
    keep_last_n: int | None = Field(default=None, ge=1)
    max_horizon: int | None = Field(default=None, ge=1)
    horizons: list[int] | None = None
    horizon_features: dict[int, list[str]] | None = None
    horizon_feature_templates: list[str] | None = None
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

    @field_validator("cv_refit")
    @classmethod
    def validate_cv_refit(cls, value: bool | int) -> bool | int:
        if isinstance(value, int) and not isinstance(value, bool) and value < 0:
            raise ValueError("cv_refit integer must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_model_options(self) -> CoreConfig:
        for field_name, values in (
            ("model_params", self.model_params),
            ("models_fit_kwargs", self.models_fit_kwargs),
        ):
            unknown = sorted(set(values) - set(self.models))
            if unknown:
                raise ValueError(f"{field_name} reference unselected models: {unknown}")
        if self.max_horizon is not None and self.horizons is not None:
            raise ValueError("max_horizon and horizons are mutually exclusive")
        if self.horizon_features is not None and self.horizon_feature_templates is not None:
            raise ValueError(
                "horizon_features and horizon_feature_templates are mutually exclusive"
            )
        if (self.horizon_features is not None or self.horizon_feature_templates is not None) and (
            self.max_horizon is None and self.horizons is None
        ):
            raise ValueError("horizon-specific features require max_horizon or horizons")
        return self


class AutoConfig(BaseModel):
    """Arguments mapped to AutoMLForecast 1.1.0 constructor and fit APIs."""

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
    dropna: bool = True
    keep_last_n: int | None = Field(default=None, ge=1)
    max_horizon: int | None = Field(default=None, ge=1)
    horizons: list[int] | None = None
    horizon_features: dict[int, list[str]] | None = None
    horizon_feature_templates: list[str] | None = None
    fitted: bool = False
    as_numpy: bool = False
    weight_col: str | None = None
    validate_data: bool = True
    cache_train_df: bool = True
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

    @field_validator("horizons")
    @classmethod
    def validate_horizons(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        normalized = sorted({int(value) for value in values})
        if not normalized or normalized[0] < 1:
            raise ValueError("horizons must contain positive integers")
        return normalized

    @field_validator("refit")
    @classmethod
    def validate_refit(cls, value: bool | int) -> bool | int:
        if isinstance(value, int) and not isinstance(value, bool) and value < 0:
            raise ValueError("refit integer must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_options(self) -> AutoConfig:
        unknown = sorted(set(self.search_spaces) - set(self.models))
        if unknown:
            raise ValueError(f"search spaces reference unselected models: {unknown}")
        if self.max_horizon is not None and self.horizons is not None:
            raise ValueError("max_horizon and horizons are mutually exclusive")
        if self.horizon_features is not None and self.horizon_feature_templates is not None:
            raise ValueError(
                "horizon_features and horizon_feature_templates are mutually exclusive"
            )
        if (self.horizon_features is not None or self.horizon_feature_templates is not None) and (
            self.max_horizon is None and self.horizons is None
        ):
            raise ValueError("horizon-specific features require max_horizon or horizons")
        return self


class MLForecastRunConfig(BaseModel):
    """Leakage-safe execution contract for MLForecast and AutoMLForecast."""

    model_config = ConfigDict(extra="forbid")

    required_mlforecast_version: Literal["1.1.0"] = "1.1.0"
    mode: RunMode = RunMode.CORE
    id_col: str = "unique_id"
    time_col: str = "ds"
    target_col: str = "y"
    static_features: list[str] = Field(default_factory=list)
    known_future_features: list[str] = Field(default_factory=list)
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
    def validate_run_contract(self) -> MLForecastRunConfig:
        if self.h != self.holdout_size:
            raise ValueError("h must equal holdout_size for an exact holdout comparison")
        reserved = {self.id_col, self.time_col, self.target_col}
        declared = self.static_features + self.known_future_features
        if len(declared) != len(set(declared)):
            raise ValueError("static and known-future feature declarations must be unique")
        invalid = sorted(reserved.intersection(declared))
        if invalid:
            raise ValueError(f"reserved columns cannot be declared as features: {invalid}")
        weight_col = self.core.weight_col if self.mode is RunMode.CORE else self.auto.weight_col
        if weight_col is not None and weight_col in declared:
            raise ValueError("weight_col cannot also be static or known-future feature")
        return self
