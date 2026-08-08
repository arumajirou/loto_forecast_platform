from __future__ import annotations

import importlib
import inspect
import time
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .argument_validator import classify_arguments
from .executor import execute_fit_predict
from .protocol import DartsRequest, ModelIdentity, SeriesLayout


class LocalModelFamily(StrEnum):
    BASELINE = "baseline"
    STATISTICAL = "statistical"


class LocalModelSpec(BaseModel):
    """Campaign-owned policy for one Darts local model candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    public_name: str
    family: LocalModelFamily
    minimum_history: int = Field(ge=1)
    optional_dependency: str | None = None
    duplicate_provider: str | None = None
    notes: str


P5_LOCAL_MODEL_SPECS: tuple[LocalModelSpec, ...] = (
    LocalModelSpec(
        public_name="NaiveMean",
        family=LocalModelFamily.BASELINE,
        minimum_history=2,
        notes="Campaign baseline; constructor and lifecycle signatures require runtime inspection.",
    ),
    LocalModelSpec(
        public_name="NaiveSeasonal",
        family=LocalModelFamily.BASELINE,
        minimum_history=2,
        notes="Season length is user-configurable and never inferred from Holdout data.",
    ),
    LocalModelSpec(
        public_name="NaiveDrift",
        family=LocalModelFamily.BASELINE,
        minimum_history=2,
        notes="Point baseline used by the existing regression ensemble route.",
    ),
    LocalModelSpec(
        public_name="NaiveMovingAverage",
        family=LocalModelFamily.BASELINE,
        minimum_history=3,
        notes="Window configuration is explicit and validated against the runtime signature.",
    ),
    LocalModelSpec(
        public_name="ARIMA",
        family=LocalModelFamily.STATISTICAL,
        minimum_history=8,
        notes="Order and trend arguments are caller-owned; no automatic repair is applied.",
    ),
    LocalModelSpec(
        public_name="AutoARIMA",
        family=LocalModelFamily.STATISTICAL,
        minimum_history=12,
        optional_dependency="runtime-discovered",
        duplicate_provider="standalone StatsForecast comparison required",
        notes="Optional dependency and wrapper identity are retained as runtime evidence.",
    ),
    LocalModelSpec(
        public_name="ExponentialSmoothing",
        family=LocalModelFamily.STATISTICAL,
        minimum_history=4,
        notes="Trend and seasonal settings are explicit campaign parameters.",
    ),
    LocalModelSpec(
        public_name="Theta",
        family=LocalModelFamily.STATISTICAL,
        minimum_history=4,
        notes="Theta configuration is passed without silent argument deletion.",
    ),
    LocalModelSpec(
        public_name="Croston",
        family=LocalModelFamily.STATISTICAL,
        minimum_history=4,
        notes="Intermittent-demand candidate; lottery suitability must be decided by OOF evidence.",
    ),
)

_SPEC_BY_NAME = {spec.public_name: spec for spec in P5_LOCAL_MODEL_SPECS}
_LIFECYCLE_METHODS = ("fit", "predict", "save", "load")
_SUPPORT_PROPERTIES = (
    "supports_past_covariates",
    "supports_future_covariates",
    "supports_static_covariates",
    "supports_multivariate",
    "supports_probabilistic_prediction",
    "supports_sample_weight",
)


def _signature(value: Any) -> str | None:
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return None


def _support_value(model_cls: type[Any], name: str) -> bool | str | None:
    value = getattr(model_cls, name, None)
    if isinstance(value, bool):
        return value
    if isinstance(value, property) or callable(value):
        return "RUNTIME_INSTANCE_REQUIRED"
    return None


def local_model_inventory(models_module: Any | None = None) -> list[dict[str, Any]]:
    """Return every P5 candidate, retaining missing imports instead of hiding them."""

    if models_module is None:
        try:
            models_module = importlib.import_module("darts.models")
        except (ImportError, ModuleNotFoundError) as exc:
            return [
                {
                    **spec.model_dump(mode="json"),
                    "status": "DEPENDENCY_MISSING",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                for spec in P5_LOCAL_MODEL_SPECS
            ]

    rows: list[dict[str, Any]] = []
    for spec in P5_LOCAL_MODEL_SPECS:
        try:
            model_cls = getattr(models_module, spec.public_name)
        except AttributeError as exc:
            rows.append(
                {
                    **spec.model_dump(mode="json"),
                    "status": "DEPENDENCY_MISSING",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            continue

        lifecycle = {
            method: _signature(getattr(model_cls, method, None)) for method in _LIFECYCLE_METHODS
        }
        support = {name: _support_value(model_cls, name) for name in _SUPPORT_PROPERTIES}
        rows.append(
            {
                **spec.model_dump(mode="json"),
                "status": "AVAILABLE_NOT_EXECUTED",
                "class_name": getattr(model_cls, "__name__", spec.public_name),
                "constructor_signature": _signature(model_cls),
                "lifecycle_signatures": lifecycle,
                "support_properties": support,
            }
        )
    return rows


def _selected_specs(model_names: Sequence[str] | None) -> tuple[LocalModelSpec, ...]:
    if model_names is None:
        return P5_LOCAL_MODEL_SPECS
    unknown = sorted(set(model_names) - set(_SPEC_BY_NAME))
    if unknown:
        raise ValueError(f"unknown P5 local models: {unknown}")
    if len(set(model_names)) != len(model_names):
        raise ValueError("model_names must not contain duplicates")
    return tuple(_SPEC_BY_NAME[name] for name in model_names)


def build_local_model_requests(
    template: DartsRequest,
    *,
    model_names: Sequence[str] | None = None,
    model_args_by_name: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[DartsRequest]:
    """Create a fair position-local request for each selected P5 candidate."""

    if template.mode != "fit_predict":
        raise ValueError("local model matrix requires mode=fit_predict")
    if template.series_layout != SeriesLayout.POSITION_LOCAL:
        raise ValueError("P5 local models require series_layout=position_local")

    selected = _selected_specs(model_names)
    overrides = dict(model_args_by_name or {})
    unknown_overrides = sorted(set(overrides) - {spec.public_name for spec in selected})
    if unknown_overrides:
        raise ValueError(f"model_args contain unselected or unknown models: {unknown_overrides}")

    requests: list[DartsRequest] = []
    for spec in selected:
        requests.append(
            template.model_copy(
                deep=True,
                update={
                    "run_id": f"{template.run_id}-{spec.public_name.lower()}",
                    "model": ModelIdentity(public_name=spec.public_name),
                    "model_args": dict(overrides.get(spec.public_name, {})),
                    "base_model_args": {},
                },
            )
        )
    return requests


def _validate_lifecycle_arguments(
    model_cls: type[Any], request: DartsRequest
) -> list[dict[str, Any]]:
    _, fit_ledger = classify_arguments(model_cls.fit, request.fit_args)
    _, predict_ledger = classify_arguments(model_cls.predict, request.predict_args)
    return [{"stage": "fit", **decision.model_dump(mode="json")} for decision in fit_ledger] + [
        {"stage": "predict", **decision.model_dump(mode="json")} for decision in predict_ledger
    ]


def run_local_model_matrix(
    template: DartsRequest,
    frame: pd.DataFrame,
    *,
    model_names: Sequence[str] | None = None,
    model_args_by_name: Mapping[str, Mapping[str, Any]] | None = None,
    models_module: Any | None = None,
    timeseries_cls: Any | None = None,
) -> list[dict[str, Any]]:
    """Execute all P5 candidates independently and retain every failure row."""

    requests = build_local_model_requests(
        template,
        model_names=model_names,
        model_args_by_name=model_args_by_name,
    )
    selected = _selected_specs(model_names)
    snapshot = frame.copy(deep=True)

    if models_module is None:
        try:
            models_module = importlib.import_module("darts.models")
        except (ImportError, ModuleNotFoundError) as exc:
            return [
                {
                    "model": spec.public_name,
                    "status": "DEPENDENCY_MISSING",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                for spec in selected
            ]

    rows: list[dict[str, Any]] = []
    for spec, request in zip(selected, requests, strict=True):
        started = time.perf_counter()
        try:
            if len(frame) < spec.minimum_history + request.horizon:
                raise ValueError(
                    f"{spec.public_name} requires at least "
                    f"{spec.minimum_history + request.horizon} rows for this campaign"
                )
            model_cls = getattr(models_module, spec.public_name)
            lifecycle_ledger = _validate_lifecycle_arguments(model_cls, request)
            predictions, constructor_ledger, metadata = execute_fit_predict(
                request,
                frame,
                models_module=models_module,
                timeseries_cls=timeseries_cls,
            )
            array = np.asarray(predictions, dtype=float)
            expected_shape = (request.geometry.positions, request.horizon)
            if array.shape != expected_shape:
                raise ValueError(
                    f"prediction shape {array.shape} does not match expected {expected_shape}"
                )
            if not np.isfinite(array).all():
                raise ValueError("prediction matrix contains NaN or Inf")
            rows.append(
                {
                    "model": spec.public_name,
                    "family": spec.family,
                    "status": "SUCCEEDED_FAKE_OR_REAL_RUNTIME",
                    "prediction_shape": list(array.shape),
                    "finite": True,
                    "constructor_argument_ledger": constructor_ledger,
                    "lifecycle_argument_ledger": lifecycle_ledger,
                    "metadata": metadata,
                    "runtime_seconds": time.perf_counter() - started,
                }
            )
        except (ImportError, ModuleNotFoundError, AttributeError) as exc:
            rows.append(
                {
                    "model": spec.public_name,
                    "family": spec.family,
                    "status": "DEPENDENCY_MISSING",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "runtime_seconds": time.perf_counter() - started,
                }
            )
        except ValueError as exc:
            rows.append(
                {
                    "model": spec.public_name,
                    "family": spec.family,
                    "status": "INVALID_REQUEST",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "runtime_seconds": time.perf_counter() - started,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "model": spec.public_name,
                    "family": spec.family,
                    "status": "EXECUTION_FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "runtime_seconds": time.perf_counter() - started,
                }
            )

    pd.testing.assert_frame_equal(frame, snapshot, check_exact=True)
    return rows
