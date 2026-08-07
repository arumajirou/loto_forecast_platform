from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import pandas as pd

from .argument_validator import classify_arguments
from .artifacts import seal_predictions
from .certification import certify_model_roundtrip
from .evaluation import evaluate_predictions, generate_baselines
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


def _split_evaluation_frame(
    request: DartsRequest,
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, np.ndarray | None]:
    if not request.evaluation.enabled:
        return frame, None
    holdout = request.evaluation.holdout_size
    if len(frame) <= holdout:
        raise ValueError("evaluation holdout leaves no training rows")
    train = frame.iloc[:-holdout].copy(deep=True)
    actual = frame.iloc[-holdout:][request.geometry.position_columns].to_numpy(float).T
    return train, actual


def execute_fit_predict(
    request: DartsRequest,
    frame: pd.DataFrame,
    *,
    models_module: Any | None = None,
    timeseries_cls: Any | None = None,
) -> tuple[
    list[list[float]],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, dict[str, Any]] | None,
    list[dict[str, Any]] | None,
    dict[str, Any] | None,
]:
    if request.model is None:
        raise ValueError("model identity is required")
    if request.series_layout != SeriesLayout.POSITION_LOCAL:
        raise ValueError("P1 provider supports position_local only")

    training_frame, actual = _split_evaluation_frame(request, frame)
    module = models_module or importlib.import_module(request.model.module)
    wrapper_cls = getattr(module, request.model.public_name)
    wrapper_args, ledger = classify_arguments(wrapper_cls, request.model_args)
    payload = build_position_local(training_frame, request.geometry)
    dart_series = to_darts_local(payload, timeseries_cls)

    all_predictions: list[list[float]] = []
    certifications: list[dict[str, Any]] = []
    component_names: list[str] = []
    for position, series in enumerate(dart_series, start=1):
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
        if request.persistence.save_model:
            artifact_path = request.artifact_dir / "models" / f"position-{position}.model"
            if request.persistence.verify_save_load:
                result = certify_model_roundtrip(
                    model=model,
                    initial_prediction=prediction,
                    artifact_path=artifact_path,
                    horizon=request.horizon,
                    predict_args=request.predict_args,
                    rtol=request.persistence.rtol,
                    atol=request.persistence.atol,
                )
            else:
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                model.save(str(artifact_path))
                result = {
                    "artifact_path": str(artifact_path),
                    "model_class": type(model).__name__,
                    "status": "SAVED_UNVERIFIED",
                }
            certifications.append(result)

    metrics = None
    baseline_metrics = None
    if actual is not None:
        metrics = evaluate_predictions(
            actual,
            all_predictions,
            tolerance=request.evaluation.tolerance,
        )
        baseline_metrics = {
            name: evaluate_predictions(actual, values, tolerance=request.evaluation.tolerance)
            for name, values in generate_baselines(
                training_frame,
                request.geometry,
                request.evaluation,
                seed=request.seed,
            ).items()
        }

    prospective_seal = None
    if request.prospective.seal_predictions:
        prospective_seal = seal_predictions(request.run_id, all_predictions)

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
            "training_rows": len(training_frame),
            "holdout_rows": request.evaluation.holdout_size if actual is not None else 0,
        },
        metrics,
        baseline_metrics,
        certifications or None,
        prospective_seal,
    )
