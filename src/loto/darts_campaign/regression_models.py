from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .argument_validator import classify_arguments
from .protocol import GameGeometry
from .timeseries_adapter import build_position_local, validate_panel

REGRESSION_MODEL_IDENTITIES: tuple[str, ...] = (
    "LinearRegressionModel",
    "RandomForestModel",
    "LightGBMModel",
    "XGBModel",
    "CatBoostModel",
    "SKLearnModel",
)


class RegressionLagContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lags: tuple[int, ...]
    lags_past_covariates: tuple[int, ...] = ()
    lags_future_covariates: tuple[int, ...] = ()
    output_chunk_length: int = Field(default=1, ge=1, le=512)
    output_chunk_shift: int = Field(default=0, ge=0, le=512)
    multi_models: bool = True
    use_static_covariates: bool = False
    categorical_past_covariates: tuple[str, ...] = ()
    categorical_future_covariates: tuple[str, ...] = ()
    likelihood: str | None = None
    quantiles: tuple[float, ...] = ()
    random_state: int = 1

    @field_validator("lags", "lags_past_covariates")
    @classmethod
    def require_negative_lags(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        normalized = tuple(sorted(set(value)))
        if not normalized and cls.__name__ == "RegressionLagContract":
            return normalized
        if any(lag >= 0 for lag in normalized):
            raise ValueError("target and past-covariate lags must be negative")
        return normalized

    @field_validator("lags_future_covariates")
    @classmethod
    def normalize_future_lags(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(sorted(set(value)))

    @field_validator("quantiles")
    @classmethod
    def validate_quantiles(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        normalized = tuple(sorted(set(float(item) for item in value)))
        if any(item <= 0.0 or item >= 1.0 for item in normalized):
            raise ValueError("quantiles must be strictly between zero and one")
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> RegressionLagContract:
        if not self.lags:
            raise ValueError("lags must contain at least one negative lag")
        if self.quantiles and self.likelihood is None:
            raise ValueError("quantiles require an explicit likelihood")
        if not self.lags_past_covariates and self.categorical_past_covariates:
            raise ValueError("categorical past covariates require past-covariate lags")
        if not self.lags_future_covariates and self.categorical_future_covariates:
            raise ValueError("categorical future covariates require future-covariate lags")
        return self

    def constructor_args(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "lags": list(self.lags),
            "output_chunk_length": self.output_chunk_length,
            "output_chunk_shift": self.output_chunk_shift,
            "multi_models": self.multi_models,
            "use_static_covariates": self.use_static_covariates,
            "random_state": self.random_state,
        }
        optional = {
            "lags_past_covariates": self.lags_past_covariates,
            "lags_future_covariates": self.lags_future_covariates,
            "categorical_past_covariates": self.categorical_past_covariates,
            "categorical_future_covariates": self.categorical_future_covariates,
            "quantiles": self.quantiles,
        }
        for key, value in optional.items():
            if value:
                payload[key] = list(value)
        if self.likelihood is not None:
            payload["likelihood"] = self.likelihood
        return payload


class RegressionModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    public_name: str
    estimator_id: str | None = None
    model_args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity(self) -> RegressionModelConfig:
        if self.public_name not in REGRESSION_MODEL_IDENTITIES:
            raise ValueError(f"unsupported regression model: {self.public_name}")
        if self.public_name == "SKLearnModel" and not self.estimator_id:
            raise ValueError("SKLearnModel requires estimator_id")
        if self.public_name != "SKLearnModel" and self.estimator_id is not None:
            raise ValueError("estimator_id is only valid for SKLearnModel")
        return self


class RegressionCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    models: tuple[RegressionModelConfig, ...]
    lag_contract: RegressionLagContract
    series_layout: Literal["position_local", "position_global_sequence"]
    horizon: int = Field(default=1, ge=1, le=512)
    seed: int = 1
    past_covariate_columns: tuple[str, ...] = ()
    future_covariate_columns: tuple[str, ...] = ()
    static_covariate_columns: tuple[str, ...] = ()
    fit_args: dict[str, Any] = Field(default_factory=dict)
    predict_args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_campaign(self) -> RegressionCampaignConfig:
        names = [item.public_name for item in self.models]
        if len(set(names)) != len(names):
            raise ValueError("regression model identities must be unique")
        if self.seed != self.lag_contract.random_state:
            raise ValueError("campaign seed must equal lag-contract random_state")
        if self.lag_contract.lags_past_covariates and not self.past_covariate_columns:
            raise ValueError("past covariate lags require past_covariate_columns")
        if self.lag_contract.lags_future_covariates and not self.future_covariate_columns:
            raise ValueError("future covariate lags require future_covariate_columns")
        if self.lag_contract.use_static_covariates and not self.static_covariate_columns:
            raise ValueError("static covariates require static_covariate_columns")
        return self


@dataclass(frozen=True)
class RegressionModelResult:
    model_name: str
    status: str
    predictions: tuple[tuple[float, ...], ...] | None
    failure_class: str | None
    message: str | None
    argument_ledger: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CovariatePayload:
    values: pd.DataFrame
    columns: tuple[str, ...]


def _validate_covariate_frame(
    frame: pd.DataFrame,
    *,
    draw_no_col: str,
    columns: Sequence[str],
    forbidden_columns: Sequence[str],
    required_start: int,
    required_end: int,
) -> CovariatePayload:
    if not columns:
        raise ValueError("covariate column list must not be empty")
    missing = [column for column in (draw_no_col, *columns) if column not in frame.columns]
    if missing:
        raise ValueError(f"missing covariate columns: {missing}")
    overlap = sorted(set(columns) & set(forbidden_columns))
    if overlap:
        raise ValueError(f"target columns cannot be reused as covariates: {overlap}")

    draw_no = pd.to_numeric(frame[draw_no_col], errors="raise").to_numpy()
    if not np.equal(draw_no, np.floor(draw_no)).all():
        raise ValueError("covariate draw numbers must be integers")
    draw_no = draw_no.astype(np.int64)
    if len(np.unique(draw_no)) != len(draw_no):
        raise ValueError("covariate draw numbers must be unique")
    if len(draw_no) > 1 and not np.all(np.diff(draw_no) == 1):
        raise ValueError("covariate draw numbers must be increasing and gap-free")
    if int(draw_no[0]) > required_start or int(draw_no[-1]) < required_end:
        raise ValueError(
            "covariate coverage is insufficient: "
            f"required={required_start}..{required_end}, "
            f"actual={int(draw_no[0])}..{int(draw_no[-1])}"
        )

    values = frame.loc[:, columns].apply(pd.to_numeric, errors="raise").copy(deep=True)
    if not np.isfinite(values.to_numpy(float)).all():
        raise ValueError("covariates must contain only finite values")
    values.index = pd.RangeIndex(
        start=int(draw_no[0]),
        stop=int(draw_no[-1]) + 1,
        step=1,
        name=draw_no_col,
    )
    return CovariatePayload(values=values, columns=tuple(columns))


def _to_darts_covariates(payload: CovariatePayload, timeseries_cls: Any) -> Any:
    return timeseries_cls.from_dataframe(payload.values)


def _prediction_array(prediction: Any) -> np.ndarray:
    values = prediction.values() if hasattr(prediction, "values") else prediction
    array = np.asarray(values, dtype=float).reshape(-1)
    if not np.isfinite(array).all():
        raise ValueError("prediction contains NaN or Inf")
    return array


def _resolve_model_class(models_module: Any, name: str) -> type[Any]:
    try:
        return getattr(models_module, name)
    except AttributeError as exc:
        raise ModuleNotFoundError(f"darts.models.{name} is unavailable") from exc


def _build_constructor_args(
    model_config: RegressionModelConfig,
    campaign: RegressionCampaignConfig,
    model_cls: type[Any],
    estimator_factories: Mapping[str, Callable[[], Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    common = campaign.lag_contract.constructor_args()
    collisions = sorted(set(common) & set(model_config.model_args))
    if collisions:
        raise ValueError(f"model_args cannot override fairness contract: {collisions}")
    requested = {**common, **model_config.model_args}
    if model_config.public_name == "SKLearnModel":
        estimator_id = model_config.estimator_id
        if estimator_id not in estimator_factories:
            raise ModuleNotFoundError(f"estimator factory is unavailable: {estimator_id}")
        requested["model"] = estimator_factories[estimator_id]()
    effective, decisions = classify_arguments(model_cls, requested)
    return effective, [item.model_dump(mode="json") for item in decisions]


def _method_kwargs(method: Callable[..., Any], requested: Mapping[str, Any]) -> dict[str, Any]:
    effective, _ = classify_arguments(method, requested)
    return effective


def _attach_static_covariates(
    series: list[Any],
    static_covariates: pd.DataFrame | None,
    campaign: RegressionCampaignConfig,
    geometry: GameGeometry,
) -> list[Any]:
    if not campaign.lag_contract.use_static_covariates:
        return series
    if static_covariates is None:
        raise ValueError("static covariates are required by the lag contract")
    required = ["position", *campaign.static_covariate_columns]
    missing = [column for column in required if column not in static_covariates.columns]
    if missing:
        raise ValueError(f"missing static covariate columns: {missing}")
    if static_covariates["position"].duplicated().any():
        raise ValueError("static covariate position values must be unique")
    indexed = static_covariates.set_index("position")
    expected = list(range(1, geometry.positions + 1))
    if sorted(indexed.index.tolist()) != expected:
        raise ValueError("static covariates must contain one row per position")
    attached: list[Any] = []
    for position, item in enumerate(series, start=1):
        row = indexed.loc[[position], campaign.static_covariate_columns].copy(deep=True)
        values = row.to_numpy(float)
        if not np.isfinite(values).all():
            raise ValueError("static covariates must contain only finite values")
        attached.append(item.with_static_covariates(row))
    return attached


def build_mlforecast_parity_payload(
    campaign: RegressionCampaignConfig,
    *,
    fold_contract: Mapping[str, Any],
) -> dict[str, Any]:
    estimators = {
        item.public_name: item.estimator_id or item.public_name for item in campaign.models
    }
    payload = {
        "schema_version": 1,
        "models": estimators,
        "lags": list(campaign.lag_contract.lags),
        "lags_past_covariates": list(campaign.lag_contract.lags_past_covariates),
        "lags_future_covariates": list(campaign.lag_contract.lags_future_covariates),
        "output_chunk_length": campaign.lag_contract.output_chunk_length,
        "output_chunk_shift": campaign.lag_contract.output_chunk_shift,
        "past_covariate_columns": list(campaign.past_covariate_columns),
        "future_covariate_columns": list(campaign.future_covariate_columns),
        "static_covariate_columns": list(campaign.static_covariate_columns),
        "horizon": campaign.horizon,
        "seed": campaign.seed,
        "fold_contract": dict(fold_contract),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def run_regression_matrix(
    campaign: RegressionCampaignConfig,
    frame: pd.DataFrame,
    geometry: GameGeometry,
    *,
    models_module: Any | None = None,
    timeseries_cls: Any | None = None,
    estimator_factories: Mapping[str, Callable[[], Any]] | None = None,
    past_covariates: pd.DataFrame | None = None,
    future_covariates: pd.DataFrame | None = None,
    static_covariates: pd.DataFrame | None = None,
) -> list[RegressionModelResult]:
    source_snapshot = frame.copy(deep=True)
    validated = validate_panel(frame, geometry)
    target_payload = build_position_local(validated, geometry)
    if timeseries_cls is None:
        from darts import TimeSeries

        timeseries_cls = TimeSeries
    target_series = [timeseries_cls.from_series(item) for item in target_payload.series]
    target_series = _attach_static_covariates(
        target_series,
        static_covariates,
        campaign,
        geometry,
    )

    target_start = int(validated[geometry.draw_no_col].iloc[0])
    target_end = int(validated[geometry.draw_no_col].iloc[-1])
    prediction_end = (
        target_end
        + campaign.horizon
        + campaign.lag_contract.output_chunk_shift
        + max((0, *campaign.lag_contract.lags_future_covariates))
    )
    past_series = None
    if campaign.past_covariate_columns:
        if past_covariates is None:
            raise ValueError("past_covariates frame is required")
        payload = _validate_covariate_frame(
            past_covariates,
            draw_no_col=geometry.draw_no_col,
            columns=campaign.past_covariate_columns,
            forbidden_columns=geometry.position_columns,
            required_start=target_start,
            required_end=prediction_end,
        )
        past_series = _to_darts_covariates(payload, timeseries_cls)
    future_series = None
    if campaign.future_covariate_columns:
        if future_covariates is None:
            raise ValueError("future_covariates frame is required")
        payload = _validate_covariate_frame(
            future_covariates,
            draw_no_col=geometry.draw_no_col,
            columns=campaign.future_covariate_columns,
            forbidden_columns=geometry.position_columns,
            required_start=target_start,
            required_end=prediction_end,
        )
        future_series = _to_darts_covariates(payload, timeseries_cls)

    module = models_module or importlib.import_module("darts.models")
    factories = estimator_factories or {}
    results: list[RegressionModelResult] = []
    for model_config in campaign.models:
        ledger: list[dict[str, Any]] = []
        try:
            model_cls = _resolve_model_class(module, model_config.public_name)
            constructor_args, ledger = _build_constructor_args(
                model_config,
                campaign,
                model_cls,
                factories,
            )
            predictions: list[tuple[float, ...]] = []
            if campaign.series_layout == "position_local":
                for series in target_series:
                    model = model_cls(**constructor_args)
                    fit_requested = dict(campaign.fit_args)
                    if past_series is not None:
                        fit_requested["past_covariates"] = past_series
                    if future_series is not None:
                        fit_requested["future_covariates"] = future_series
                    model.fit(series, **_method_kwargs(model.fit, fit_requested))
                    predict_requested = dict(campaign.predict_args)
                    if past_series is not None:
                        predict_requested["past_covariates"] = past_series
                    if future_series is not None:
                        predict_requested["future_covariates"] = future_series
                    prediction = model.predict(
                        campaign.horizon,
                        **_method_kwargs(model.predict, predict_requested),
                    )
                    values = _prediction_array(prediction)
                    if values.size != campaign.horizon:
                        raise ValueError("prediction shape does not match horizon")
                    predictions.append(tuple(values.tolist()))
            else:
                model = model_cls(**constructor_args)
                fit_requested = dict(campaign.fit_args)
                if past_series is not None:
                    fit_requested["past_covariates"] = [past_series] * geometry.positions
                if future_series is not None:
                    fit_requested["future_covariates"] = [future_series] * geometry.positions
                model.fit(target_series, **_method_kwargs(model.fit, fit_requested))
                predict_requested = {**campaign.predict_args, "series": target_series}
                if past_series is not None:
                    predict_requested["past_covariates"] = [past_series] * geometry.positions
                if future_series is not None:
                    predict_requested["future_covariates"] = [future_series] * geometry.positions
                prediction_list = model.predict(
                    campaign.horizon,
                    **_method_kwargs(model.predict, predict_requested),
                )
                if not isinstance(prediction_list, Sequence):
                    raise ValueError("global regression prediction must return a sequence")
                for prediction in prediction_list:
                    values = _prediction_array(prediction)
                    if values.size != campaign.horizon:
                        raise ValueError("prediction shape does not match horizon")
                    predictions.append(tuple(values.tolist()))
            if len(predictions) != geometry.positions:
                raise ValueError("prediction position count does not match geometry")
            results.append(
                RegressionModelResult(
                    model_name=model_config.public_name,
                    status="SUCCEEDED",
                    predictions=tuple(predictions),
                    failure_class=None,
                    message=None,
                    argument_ledger=tuple(ledger),
                    metadata={
                        "series_layout": campaign.series_layout,
                        "positions": geometry.positions,
                        "horizon": campaign.horizon,
                        "seed": campaign.seed,
                        "estimator_id": model_config.estimator_id,
                    },
                )
            )
        except (ImportError, ModuleNotFoundError) as exc:
            results.append(
                RegressionModelResult(
                    model_name=model_config.public_name,
                    status="FAILED",
                    predictions=None,
                    failure_class="DEPENDENCY_MISSING",
                    message=str(exc),
                    argument_ledger=tuple(ledger),
                    metadata={"seed": campaign.seed},
                )
            )
        except ValueError as exc:
            results.append(
                RegressionModelResult(
                    model_name=model_config.public_name,
                    status="FAILED",
                    predictions=None,
                    failure_class="INVALID_REQUEST",
                    message=str(exc),
                    argument_ledger=tuple(ledger),
                    metadata={"seed": campaign.seed},
                )
            )
        except Exception as exc:
            results.append(
                RegressionModelResult(
                    model_name=model_config.public_name,
                    status="FAILED",
                    predictions=None,
                    failure_class="RUNTIME_FAILED",
                    message=f"{type(exc).__name__}: {exc}",
                    argument_ledger=tuple(ledger),
                    metadata={"seed": campaign.seed},
                )
            )
    pd.testing.assert_frame_equal(frame, source_snapshot)
    return results


def signature_contract(target: Callable[..., Any]) -> str:
    return str(inspect.signature(target))
