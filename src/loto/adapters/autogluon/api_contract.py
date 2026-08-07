from __future__ import annotations

from typing import Any

TARGET_AUTOGLUON_VERSION = "1.5.0"

TIME_SERIES_PREDICTOR_INIT_ARGUMENTS = frozenset(
    {
        "target",
        "known_covariates_names",
        "prediction_length",
        "freq",
        "eval_metric",
        "eval_metric_seasonal_period",
        "horizon_weight",
        "path",
        "verbosity",
        "quantile_levels",
        "cache_predictions",
    }
)

TIME_SERIES_PREDICTOR_FIT_ARGUMENTS = frozenset(
    {
        "time_limit",
        "presets",
        "hyperparameters",
        "hyperparameter_tune_kwargs",
        "excluded_model_types",
        "ensemble_hyperparameters",
        "num_val_windows",
        "val_step_size",
        "refit_every_n_windows",
        "refit_full",
        "enable_ensemble",
        "skip_model_selection",
        "random_seed",
        "verbosity",
    }
)

TIME_SERIES_PREDICTOR_PREDICT_ARGUMENTS = frozenset(
    {
        "known_covariates",
        "model",
        "use_cache",
        "random_seed",
    }
)

HPO_PRESETS = frozenset({"auto", "random"})
HPO_DICT_KEYS = frozenset({"num_trials", "scheduler", "searcher"})
HPO_SCHEDULERS = frozenset({"local"})
HPO_SEARCHERS = frozenset({"local_random", "random", "bayes", "auto"})


class AutoGluonApiContractError(ValueError):
    pass


def validate_hpo_tune_kwargs(value: dict[str, Any] | str | None) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if value not in HPO_PRESETS:
            raise AutoGluonApiContractError(
                f"hyperparameter_tune_kwargs string must be one of {sorted(HPO_PRESETS)}"
            )
        return
    if not isinstance(value, dict):
        raise AutoGluonApiContractError(
            "hyperparameter_tune_kwargs must be a supported string or dictionary"
        )

    unexpected = sorted(set(value) - HPO_DICT_KEYS)
    missing = sorted(HPO_DICT_KEYS - set(value))
    if unexpected:
        raise AutoGluonApiContractError(
            f"hyperparameter_tune_kwargs contains unsupported keys: {unexpected}"
        )
    if missing:
        raise AutoGluonApiContractError(
            f"hyperparameter_tune_kwargs is missing required keys: {missing}"
        )

    num_trials = value["num_trials"]
    if isinstance(num_trials, bool) or not isinstance(num_trials, int) or num_trials <= 0:
        raise AutoGluonApiContractError(
            "hyperparameter_tune_kwargs.num_trials must be a positive integer"
        )
    scheduler = value["scheduler"]
    if scheduler not in HPO_SCHEDULERS:
        raise AutoGluonApiContractError(
            f"hyperparameter_tune_kwargs.scheduler must be one of {sorted(HPO_SCHEDULERS)}"
        )
    searcher = value["searcher"]
    if searcher not in HPO_SEARCHERS:
        raise AutoGluonApiContractError(
            f"hyperparameter_tune_kwargs.searcher must be one of {sorted(HPO_SEARCHERS)}"
        )


def validate_public_api_kwargs(
    *,
    predictor_kwargs: dict[str, Any],
    fit_kwargs: dict[str, Any],
    predict_kwargs: dict[str, Any] | None = None,
) -> None:
    checks = (
        ("TimeSeriesPredictor.__init__", predictor_kwargs, TIME_SERIES_PREDICTOR_INIT_ARGUMENTS),
        ("TimeSeriesPredictor.fit", fit_kwargs, TIME_SERIES_PREDICTOR_FIT_ARGUMENTS),
        (
            "TimeSeriesPredictor.predict",
            predict_kwargs or {},
            TIME_SERIES_PREDICTOR_PREDICT_ARGUMENTS,
        ),
    )
    for method, kwargs, allowed in checks:
        unsupported = sorted(set(kwargs) - allowed)
        if unsupported:
            raise AutoGluonApiContractError(
                f"{method} received unsupported AutoGluon {TARGET_AUTOGLUON_VERSION} "
                f"keyword arguments: {unsupported}"
            )
