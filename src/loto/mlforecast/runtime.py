from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.mlforecast.contracts import MLForecastRunConfig, RunMode
from loto.mlforecast.data import validate_future_features
from loto.mlforecast.factory import (
    auto_fit_kwargs,
    build_auto_forecast,
    build_core_forecast,
    build_prediction_intervals,
    core_fit_kwargs,
    hit_at_1_objective,
)
from loto.mlforecast.provenance import verify_mlforecast_runtime


def _prediction_columns(
    prediction: pd.DataFrame,
    *,
    id_col: str,
    time_col: str,
) -> list[str]:
    excluded = {id_col, time_col, "cutoff"}
    columns = [column for column in prediction.columns if column not in excluded]
    return [column for column in columns if "-lo-" not in column and "-hi-" not in column]


def _future_frame_for_model(model: Any, h: int) -> pd.DataFrame:
    expected = model.make_future_dataframe(h=h)
    if not isinstance(expected, pd.DataFrame):
        expected = expected.to_pandas()
    return expected


def _validated_x_df(
    model: Any,
    frame: pd.DataFrame | None,
    *,
    h: int,
    config: MLForecastRunConfig,
) -> pd.DataFrame | None:
    expected = _future_frame_for_model(model, h)
    return validate_future_features(frame, expected_keys=expected, config=config)


def _auto_loss(
    validation: pd.DataFrame,
    train_df: pd.DataFrame,
    *,
    target_col: str,
    weight_col: str | None = None,
) -> float:
    return hit_at_1_objective(
        validation,
        train_df,
        target_col=target_col,
        weight_col=weight_col,
    )


def _fit_predict(
    train: pd.DataFrame,
    holdout_features: pd.DataFrame | None,
    config: MLForecastRunConfig,
) -> tuple[Any, pd.DataFrame, dict[str, Any], dict[str, pd.DataFrame]]:
    runtime = verify_mlforecast_runtime(config.required_mlforecast_version)
    if config.mode is RunMode.CORE:
        model = build_core_forecast(config.core, seed=config.seed)
        intervals = build_prediction_intervals(config.core.prediction_intervals)
        levels = (
            config.core.prediction_intervals.levels
            if config.core.prediction_intervals
            else None
        )
        cv_prediction = model.cross_validation(
            train,
            n_windows=config.core.cv_n_windows,
            h=config.h,
            id_col=config.id_col,
            time_col=config.time_col,
            target_col=config.target_col,
            step_size=config.core.cv_step_size,
            static_features=config.static_features,
            dropna=config.core.dropna,
            keep_last_n=config.core.keep_last_n,
            refit=config.core.cv_refit,
            max_horizon=config.core.max_horizon,
            horizons=config.core.horizons,
            horizon_features=config.core.horizon_features,
            horizon_feature_templates=config.core.horizon_feature_templates,
            prediction_intervals=intervals,
            level=levels,
            input_size=config.core.cv_input_size,
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
            static_features=config.static_features,
            **core_fit_kwargs(config.core),
        )
        x_df = _validated_x_df(model, holdout_features, h=config.h, config=config)
        prediction = model.predict(h=config.h, level=levels, X_df=x_df)
        metadata = {
            "mode": "core",
            "models": config.core.models,
            "runtime": runtime,
            "static_features": config.static_features,
            "known_future_features": config.known_future_features,
        }
        return model, prediction, metadata, {"core_cv_predictions": cv_prediction}

    model = build_auto_forecast(config.auto, static_features=config.static_features)
    kwargs = auto_fit_kwargs(config.auto, seed=config.seed)
    kwargs["h"] = config.h

    def loss(
        validation: pd.DataFrame,
        train_df: pd.DataFrame,
        weight_col: str | None = None,
    ) -> float:
        return _auto_loss(
            validation,
            train_df,
            target_col=config.target_col,
            weight_col=weight_col,
        )

    model.fit(
        train,
        loss=loss,
        id_col=config.id_col,
        time_col=config.time_col,
        target_col=config.target_col,
        **{key: value for key, value in kwargs.items() if value is not None},
    )
    first_model = next(iter(model.models_.values()))
    x_df = _validated_x_df(first_model, holdout_features, h=config.h, config=config)
    levels = config.auto.prediction_intervals.levels if config.auto.prediction_intervals else None
    prediction = model.predict(h=config.h, level=levels, X_df=x_df)
    trials = {
        f"optuna_trials_{name}": study.trials_dataframe()
        for name, study in model.results_.items()
    }
    metadata = {
        "mode": "auto",
        "models": config.auto.models,
        "runtime": runtime,
        "static_features": config.static_features,
        "known_future_features": config.known_future_features,
    }
    return model, prediction, metadata, trials


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
        model_paths = {}
        for name, fitted_model in model.models_.items():
            path = model_dir / name
            path.mkdir(parents=True, exist_ok=False)
            fitted_model.save(str(path))
            model_paths[name] = path
    if not config.verify_save_load:
        paths = {key: str(value) for key, value in model_paths.items()}
        return {"status": "SAVED", "paths": paths}

    from mlforecast import MLForecast

    checks: dict[str, Any] = {}
    for bundle_name, path in model_paths.items():
        loaded = MLForecast.load(str(path))
        levels = None
        if config.mode is RunMode.CORE and config.core.prediction_intervals:
            levels = config.core.prediction_intervals.levels
        if config.mode is RunMode.AUTO and config.auto.prediction_intervals:
            levels = config.auto.prediction_intervals.levels
        x_df = _validated_x_df(loaded, holdout_features, h=config.h, config=config)
        after = loaded.predict(h=config.h, level=levels, X_df=x_df)
        before_columns = _prediction_columns(
            prediction,
            id_col=config.id_col,
            time_col=config.time_col,
        )
        after_columns = _prediction_columns(
            after,
            id_col=config.id_col,
            time_col=config.time_col,
        )
        if config.mode is RunMode.AUTO:
            before_columns = [column for column in before_columns if column == bundle_name]
            after_columns = [column for column in after_columns if column == bundle_name]
        if set(before_columns) != set(after_columns) or not before_columns:
            raise ValueError(f"prediction columns changed after loading {bundle_name}")
        bundle_checks: dict[str, Any] = {}
        for column in sorted(before_columns):
            sort_columns = [config.id_col, config.time_col]
            before_values = prediction.sort_values(sort_columns)[column].to_numpy(float)
            after_values = after.sort_values(sort_columns)[column].to_numpy(float)
            finite = bool(np.isfinite(after_values).all())
            match = bool(
                before_values.shape == after_values.shape
                and finite
                and np.allclose(before_values, after_values, rtol=1e-8, atol=1e-8)
            )
            bundle_checks[column] = {
                "shape": list(after_values.shape),
                "finite": finite,
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
        model.update(holdout, validate_new_data=True)
        levels = (
            config.core.prediction_intervals.levels
            if config.core.prediction_intervals
            else None
        )
        x_df = _validated_x_df(
            model,
            prospective_features,
            h=config.prospective_h,
            config=config,
        )
        return model.predict(h=config.prospective_h, level=levels, X_df=x_df)

    outputs: list[pd.DataFrame] = []
    levels = config.auto.prediction_intervals.levels if config.auto.prediction_intervals else None
    for name, fitted_model in model.models_.items():
        fitted_model.update(holdout, validate_new_data=True)
        x_df = _validated_x_df(
            fitted_model,
            prospective_features,
            h=config.prospective_h,
            config=config,
        )
        prediction = fitted_model.predict(h=config.prospective_h, level=levels, X_df=x_df)
        model_columns = [column for column in prediction.columns if column.startswith(name)]
        keep = [config.id_col, config.time_col, *model_columns]
        outputs.append(prediction[keep])
    result = outputs[0]
    for output in outputs[1:]:
        result = result.merge(output, on=[config.id_col, config.time_col], validate="one_to_one")
    return result
