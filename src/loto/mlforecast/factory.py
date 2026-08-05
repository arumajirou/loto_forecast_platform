from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from loto.mlforecast.contracts import (
    AutoConfig,
    CoreConfig,
    LagTransformSpec,
    PredictionIntervalsConfig,
    SearchParameter,
    TargetTransformSpec,
)


AUTO_CLASS_NAMES = {
    "AutoLightGBM": "AutoLightGBM",
    "AutoXGBoost": "AutoXGBoost",
    "AutoCatboost": "AutoCatboost",
    "AutoLinearRegression": "AutoLinearRegression",
    "AutoRidge": "AutoRidge",
    "AutoLasso": "AutoLasso",
    "AutoElasticNet": "AutoElasticNet",
    "AutoRandomForest": "AutoRandomForest",
}


def build_core_estimator(name: str, params: dict[str, Any], *, seed: int) -> Any:
    """Build one sklearn-compatible regressor without importing unused backends."""
    effective = dict(params)
    if name == "linear_regression":
        from sklearn.linear_model import LinearRegression

        return LinearRegression(**effective)
    if name == "ridge":
        from sklearn.linear_model import Ridge

        return Ridge(**effective)
    if name == "lasso":
        from sklearn.linear_model import Lasso

        effective.setdefault("max_iter", 10_000)
        return Lasso(**effective)
    if name == "elastic_net":
        from sklearn.linear_model import ElasticNet

        effective.setdefault("max_iter", 10_000)
        return ElasticNet(**effective)
    if name == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        effective.setdefault("random_state", seed)
        effective.setdefault("n_jobs", 1)
        return RandomForestRegressor(**effective)
    if name == "lightgbm":
        from lightgbm import LGBMRegressor

        effective.setdefault("random_state", seed)
        effective.setdefault("verbosity", -1)
        effective.setdefault("n_jobs", 1)
        return LGBMRegressor(**effective)
    if name == "xgboost":
        from xgboost import XGBRegressor

        effective.setdefault("random_state", seed)
        effective.setdefault("n_jobs", 1)
        return XGBRegressor(**effective)
    if name == "catboost":
        from catboost import CatBoostRegressor

        effective.setdefault("random_seed", seed)
        effective.setdefault("verbose", False)
        effective.setdefault("thread_count", 1)
        return CatBoostRegressor(**effective)
    raise ValueError(f"unsupported core MLForecast model: {name}")


def _build_lag_transform(spec: LagTransformSpec) -> Any:
    from mlforecast import lag_transforms as transforms

    classes = {
        "rolling_mean": transforms.RollingMean,
        "rolling_std": transforms.RollingStd,
        "rolling_min": transforms.RollingMin,
        "rolling_max": transforms.RollingMax,
        "expanding_mean": transforms.ExpandingMean,
        "exponentially_weighted_mean": transforms.ExponentiallyWeightedMean,
    }
    return classes[spec.kind](**spec.params)


def build_lag_transforms(
    specs: dict[int, list[LagTransformSpec]],
) -> dict[int, list[Any]] | None:
    if not specs:
        return None
    return {
        int(lag): [_build_lag_transform(spec) for spec in transforms]
        for lag, transforms in specs.items()
    }


def _build_target_transform(spec: TargetTransformSpec) -> Any:
    from mlforecast import target_transforms as transforms

    if spec.kind == "differences":
        differences = spec.params.get("differences")
        if not isinstance(differences, list) or not differences:
            raise ValueError("differences transform requires params.differences")
        return transforms.Differences([int(value) for value in differences])
    if spec.kind == "local_standard_scaler":
        if spec.params:
            raise ValueError("local_standard_scaler does not accept parameters")
        return transforms.LocalStandardScaler()
    raise ValueError(f"unsupported target transform: {spec.kind}")


def build_target_transforms(specs: list[TargetTransformSpec]) -> list[Any] | None:
    if not specs:
        return None
    return [_build_target_transform(spec) for spec in specs]


def build_prediction_intervals(config: PredictionIntervalsConfig | None) -> Any | None:
    if config is None:
        return None
    from mlforecast.utils import PredictionIntervals

    return PredictionIntervals(n_windows=config.n_windows, h=config.h, method=config.method)


def build_core_forecast(config: CoreConfig, *, seed: int) -> Any:
    """Map the strict local contract to the MLForecast 1.1.0 constructor."""
    from mlforecast import MLForecast

    models = {
        name: build_core_estimator(name, config.model_params.get(name, {}), seed=seed)
        for name in config.models
    }
    return MLForecast(
        models=models,
        freq=config.freq,
        lags=config.lags,
        lag_transforms=build_lag_transforms(config.lag_transforms),
        date_features=config.date_features or None,
        num_threads=config.num_threads,
        target_transforms=build_target_transforms(config.target_transforms),
        date_features_as_dummies=config.date_features_as_dummies,
        drop_auxiliary_columns=config.drop_auxiliary_columns,
    )


def core_fit_kwargs(config: CoreConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "static_features": config.static_features,
        "dropna": config.dropna,
        "keep_last_n": config.keep_last_n,
        "max_horizon": config.max_horizon,
        "horizons": config.horizons,
        "prediction_intervals": build_prediction_intervals(config.prediction_intervals),
        "fitted": config.fitted,
        "as_numpy": config.as_numpy,
        "weight_col": config.weight_col,
        "validate_data": config.validate_data,
        "cache_train_df": config.cache_train_df,
    }
    return {key: value for key, value in kwargs.items() if value is not None}


def _suggest_parameter(trial: Any, name: str, spec: SearchParameter) -> Any:
    if spec.kind == "categorical":
        return trial.suggest_categorical(name, spec.choices)
    if spec.kind == "int":
        kwargs: dict[str, Any] = {"log": spec.log}
        if spec.step is not None:
            kwargs["step"] = int(spec.step)
        return trial.suggest_int(name, int(spec.low), int(spec.high), **kwargs)
    kwargs = {"log": spec.log}
    if spec.step is not None:
        kwargs["step"] = float(spec.step)
    return trial.suggest_float(name, float(spec.low), float(spec.high), **kwargs)


def build_search_space(
    specs: dict[str, SearchParameter],
) -> Callable[[Any], dict[str, Any]] | None:
    if not specs:
        return None

    def config(trial: Any) -> dict[str, Any]:
        return {
            name: _suggest_parameter(trial, name, spec)
            for name, spec in sorted(specs.items())
        }

    return config


def build_auto_forecast(config: AutoConfig) -> Any:
    """Build AutoMLForecast with any subset of the eight official AutoModels."""
    from mlforecast import auto as auto_module

    models: dict[str, Any] = {}
    for name in config.models:
        cls = getattr(auto_module, AUTO_CLASS_NAMES[name])
        models[name] = cls(config=build_search_space(config.search_spaces.get(name, {})))
    return auto_module.AutoMLForecast(
        models=models,
        freq=config.freq,
        season_length=config.season_length,
        num_threads=config.num_threads,
        reuse_cv_splits=config.reuse_cv_splits,
    )


def build_sampler(name: str, *, seed: int) -> Any:
    import optuna

    if name == "tpe":
        return optuna.samplers.TPESampler(seed=seed, multivariate=True)
    if name == "random":
        return optuna.samplers.RandomSampler(seed=seed)
    if name == "qmc":
        return optuna.samplers.QMCSampler(seed=seed)
    if name == "cmaes":
        return optuna.samplers.CmaEsSampler(seed=seed)
    raise ValueError(f"unsupported sampler: {name}")


def auto_fit_kwargs(config: AutoConfig, *, seed: int) -> dict[str, Any]:
    optimize_kwargs: dict[str, Any] = {"n_jobs": config.n_jobs}
    if config.timeout_seconds is not None:
        optimize_kwargs["timeout"] = config.timeout_seconds
    return {
        "n_windows": config.n_windows,
        "h": None,
        "num_samples": config.num_samples,
        "step_size": config.step_size,
        "input_size": config.input_size,
        "refit": config.refit,
        "study_kwargs": {"sampler": build_sampler(config.sampler, seed=seed)},
        "optimize_kwargs": optimize_kwargs,
        "fitted": config.fitted,
        "prediction_intervals": build_prediction_intervals(config.prediction_intervals),
        "weight_col": config.weight_col,
    }


def hit_at_1_objective(
    validation: pd.DataFrame,
    train: pd.DataFrame,
    *,
    target_col: str = "y",
    prediction_col: str = "model",
) -> float:
    """Lexicographically prioritize fewer Hit@±1 misses, then bounded MAE.

    AutoMLForecast minimizes this scalar. One fewer miss always dominates any MAE
    improvement because the tie-break term is strictly smaller than 1.
    """
    del train
    actual = pd.to_numeric(validation[target_col], errors="raise").to_numpy(float)
    predicted = pd.to_numeric(validation[prediction_col], errors="raise").to_numpy(float)
    if actual.shape != predicted.shape or actual.size == 0:
        raise ValueError("validation actuals and predictions must be non-empty and aligned")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("validation actuals and predictions must be finite")
    errors = np.abs(predicted - actual)
    misses = int(np.count_nonzero(errors > 1.0))
    mae = float(errors.mean())
    scale = float(np.mean(np.abs(actual))) + 1.0
    bounded_mae = mae / (mae + scale)
    return float(misses + bounded_mae)
