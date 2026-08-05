from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.mlforecast.contracts import MLForecastRunConfig, RunMode
from loto.mlforecast.factory import (
    auto_fit_kwargs,
    build_auto_forecast,
    build_core_forecast,
    build_prediction_intervals,
    core_fit_kwargs,
    hit_at_1_objective,
)


def _prediction_columns(
    prediction: pd.DataFrame,
    *,
    id_col: str,
    time_col: str,
) -> list[str]:
    excluded = {id_col, time_col, "cutoff"}
    columns = [column for column in prediction.columns if column not in excluded]
    return [column for column in columns if "-lo-" not in column and "-hi-" not in column]


def _fit_predict(
    train: pd.DataFrame,
    holdout_features: pd.DataFrame | None,
    config: MLForecastRunConfig,
) -> tuple[Any, pd.DataFrame, dict[str, Any], dict[str, pd.DataFrame]]:
    if config.mode is RunMode.CORE:
        model = build_core_forecast(config.core, seed=config.seed)
        cv_prediction = model.cross_validation(
            train,
            n_windows=config.core.cv_n_windows,
            h=config.h,
            id_col=config.id_col,
            time_col=config.time_col,
            target_col=config.target_col,
            step_size=config.core.cv_step_size,
            static_features=config.core.static_features,
            dropna=config.core.dropna,
            keep_last_n=config.core.keep_last_n,
            refit=config.core.cv_refit,
            input_size=config.core.cv_input_size,
            prediction_intervals=build_prediction_intervals(config.core.prediction_intervals),
            level=(
                config.core.prediction_intervals.levels
                if config.core.prediction_intervals
                else None
            ),
            fitted=config.core.fitted,
            as_numpy=config.core.as_numpy,
            weight_col=config.core.weight_col,
            validate_data=config.core.validate_data,
        )
        model.fit(
            train,
            id_col=config.id_col,
            time_col=config.time_col,
            target_col=config.target_col,
            **core_fit_kwargs(config.core),
        )
        levels = (
            config.core.prediction_intervals.levels if config.core.prediction_intervals else None
        )
        prediction = model.predict(h=config.h, level=levels, X_df=holdout_features)
        return (
            model,
            prediction,
            {"mode": "core", "models": config.core.models},
            {"core_cv_predictions": cv_prediction},
        )

    model = build_auto_forecast(config.auto)
    kwargs = auto_fit_kwargs(config.auto, seed=config.seed)
    kwargs["h"] = config.h
    model.fit(
        train,
        loss=lambda valid, fitted_train: hit_at_1_objective(
            valid,
            fitted_train,
            target_col=config.target_col,
        ),
        id_col=config.id_col,
        time_col=config.time_col,
        target_col=config.target_col,
        **{key: value for key, value in kwargs.items() if value is not None},
    )
    levels = config.auto.prediction_intervals.levels if config.auto.prediction_intervals else None
    prediction = model.predict(h=config.h, level=levels, X_df=holdout_features)
    trials = {
        f"optuna_trials_{name}": study.trials_dataframe() for name, study in model.results_.items()
    }
    return model, prediction, {"mode": "auto", "models": config.auto.models}, trials


def _save_and_certify(
    model: Any,
    prediction: pd.DataFrame,
    model_dir: Path,
    config: MLForecastRunConfig,
    holdout_features: pd.DataFrame | None,
) -> dict[str, Any]:
    if not config.save_model:
        return {"status": "SKIPPED", "reason": "save_model=false"}
    model_dir.mkdir(parents=True, exist_ok=True)
    if config.mode is RunMode.CORE:
        model.save(str(model_dir))
        model_paths = {"core": model_dir}
    else:
        model.save(model_dir)
        model_paths = {name: model_dir / name for name in config.auto.models}
    if not config.verify_save_load:
        return {"status": "SAVED", "paths": {key: str(value) for key, value in model_paths.items()}}

    from mlforecast import MLForecast

    checks: dict[str, Any] = {}
    for bundle_name, path in model_paths.items():
        loaded = MLForecast.load(str(path))
        levels = None
        if config.mode is RunMode.CORE and config.core.prediction_intervals:
            levels = config.core.prediction_intervals.levels
        if config.mode is RunMode.AUTO and config.auto.prediction_intervals:
            levels = config.auto.prediction_intervals.levels
        after = loaded.predict(h=config.h, level=levels, X_df=holdout_features)
        before_columns = _prediction_columns(
            prediction, id_col=config.id_col, time_col=config.time_col
        )
        after_columns = _prediction_columns(after, id_col=config.id_col, time_col=config.time_col)
        if config.mode is RunMode.AUTO:
            before_columns = [column for column in before_columns if column == bundle_name]
            after_columns = [column for column in after_columns if column == bundle_name]
        if set(before_columns) != set(after_columns) or not before_columns:
            raise ValueError(f"prediction columns changed after loading {bundle_name}")
        bundle_checks: dict[str, Any] = {}
        for column in sorted(before_columns):
            before_values = prediction.sort_values([config.id_col, config.time_col])[
                column
            ].to_numpy(float)
            after_values = after.sort_values([config.id_col, config.time_col])[column].to_numpy(
                float
            )
            match = bool(
                before_values.shape == after_values.shape
                and np.isfinite(after_values).all()
                and np.allclose(before_values, after_values, rtol=1e-8, atol=1e-8)
            )
            bundle_checks[column] = {
                "shape": list(after_values.shape),
                "finite": bool(np.isfinite(after_values).all()),
                "prediction_match": match,
            }
            if not match:
                raise ValueError(f"save/load prediction mismatch for {column}")
        checks[bundle_name] = {"path": str(path), "predictions": bundle_checks}
    return {"status": "RUNTIME_CERTIFIED", "models": checks}


def _update_for_prospective(
    model: Any,
    holdout: pd.DataFrame,
    config: MLForecastRunConfig,
    prospective_features: pd.DataFrame | None,
) -> pd.DataFrame:
    if config.mode is RunMode.CORE:
        model.update(holdout)
        levels = (
            config.core.prediction_intervals.levels if config.core.prediction_intervals else None
        )
        return model.predict(h=config.prospective_h, level=levels, X_df=prospective_features)
    outputs: list[pd.DataFrame] = []
    levels = config.auto.prediction_intervals.levels if config.auto.prediction_intervals else None
    for name, fitted_model in model.models_.items():
        fitted_model.update(holdout)
        prediction = fitted_model.predict(
            h=config.prospective_h, level=levels, X_df=prospective_features
        )
        model_columns = [column for column in prediction.columns if column.startswith(name)]
        keep = [config.id_col, config.time_col, *model_columns]
        outputs.append(prediction[keep])
    result = outputs[0]
    for output in outputs[1:]:
        result = result.merge(output, on=[config.id_col, config.time_col], validate="one_to_one")
    return result
