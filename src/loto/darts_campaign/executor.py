from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import pandas as pd

from .argument_validator import classify_arguments
from .protocol import DartsRequest, SeriesLayout
from .timeseries_adapter import build_position_local, to_darts_local


def _prediction_values(prediction: Any) -> np.ndarray:
    if hasattr(prediction, "values"):
        values = prediction.values()
    else:
        values = prediction
    array = np.asarray(values, dtype=float).reshape(-1)
    if not np.isfinite(array).all():
        raise ValueError("prediction contains NaN or Inf")
    return array


def execute_fit_predict(
    request: DartsRequest,
    frame: pd.DataFrame,
    *,
    models_module: Any | None = None,
    timeseries_cls: Any | None = None,
) -> tuple[list[list[float]], list[dict[str, Any]], dict[str, Any]]:
    """Execute the first supported route: position-local models and regression ensemble."""

    if request.model is None:
        raise ValueError("model identity is required")
    if request.series_layout != SeriesLayout.POSITION_LOCAL:
        raise ValueError("P1 provider supports position_local only")

    module = models_module or importlib.import_module(request.model.module)
    wrapper_cls = getattr(module, request.model.public_name)
    wrapper_args, ledger = classify_arguments(wrapper_cls, request.model_args)
    payload = build_position_local(frame, request.geometry)
    dart_series = to_darts_local(payload, timeseries_cls)

    all_predictions: list[list[float]] = []
    component_names: list[str] = []
    for series in dart_series:
        if request.model.wrapper_name:
            base_models: list[Any] = []
            for base_name in request.model.base_models:
                base_cls = getattr(module, base_name)
                base_args, base_ledger = classify_arguments(
                    base_cls, request.base_model_args.get(base_name, {})
                )
                ledger.extend(base_ledger)
                base_models.append(base_cls(**base_args))
                component_names.append(base_name)
            model = wrapper_cls(forecasting_models=base_models, **wrapper_args)
        else:
            model = wrapper_cls(**wrapper_args)
        model.fit(series, **request.fit_args)
        prediction = model.predict(request.horizon, **request.predict_args)
        all_predictions.append(_prediction_values(prediction).tolist())

    return (
        all_predictions,
        [decision.model_dump(mode="json") for decision in ledger],
        {
            "library": "darts",
            "public_name": request.model.public_name,
            "wrapper_name": request.model.wrapper_name,
            "base_models": sorted(set(component_names)),
            "series_layout": request.series_layout,
            "positions": request.geometry.positions,
            "horizon": request.horizon,
        },
    )
