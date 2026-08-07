from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchResult:
    best_params: dict[str, Any]
    best_value: float
    trials: list[dict[str, Any]]
    backend: str


PARAM_SPACES: dict[str, dict[str, tuple]] = {
    "logistic": {"C": ("float_log", 1e-3, 100.0)},
    "extra-trees": {
        "n_estimators": ("int", 100, 800, 100),
        "min_samples_leaf": ("int", 1, 10, 1),
        "max_features": ("categorical", ["sqrt", "log2", None]),
    },
    "hist-gradient-boosting": {
        "max_iter": ("int", 100, 600, 50),
        "learning_rate": ("float_log", 0.005, 0.2),
        "max_leaf_nodes": ("int", 7, 63, 4),
        "l2_regularization": ("float_log", 1e-5, 10.0),
    },
    "lightgbm-classifier": {
        "n_estimators": ("int", 100, 1000, 100),
        "learning_rate": ("float_log", 0.005, 0.2),
        "num_leaves": ("int", 7, 127, 8),
        "min_child_samples": ("int", 5, 100, 5),
        "subsample": ("float", 0.6, 1.0),
        "colsample_bytree": ("float", 0.6, 1.0),
        "reg_alpha": ("float_log", 1e-6, 10.0),
        "reg_lambda": ("float_log", 1e-6, 10.0),
    },
    "nf-nhits": {
        "input_size": ("categorical", [16, 32, 64, 128]),
        "max_steps": ("categorical", [200, 500, 1000]),
        "learning_rate": ("float_log", 1e-5, 1e-2),
        "batch_size": ("categorical", [16, 32, 64]),
    },
    "nf-tide": {
        "input_size": ("categorical", [16, 32, 64, 128]),
        "hidden_size": ("categorical", [64, 128, 256, 512]),
        "num_encoder_layers": ("int", 1, 4, 1),
        "num_decoder_layers": ("int", 1, 4, 1),
        "learning_rate": ("float_log", 1e-5, 1e-2),
    },
}


def _suggest_optuna(trial, space: dict[str, tuple]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name, spec in space.items():
        kind = spec[0]
        if kind == "int":
            params[name] = trial.suggest_int(name, spec[1], spec[2], step=spec[3])
        elif kind == "float":
            params[name] = trial.suggest_float(name, spec[1], spec[2])
        elif kind == "float_log":
            params[name] = trial.suggest_float(name, spec[1], spec[2], log=True)
        elif kind == "categorical":
            params[name] = trial.suggest_categorical(name, spec[1])
        else:
            raise ValueError(f"unsupported search-space type: {kind}")
    return params


def optimize_optuna(
    model_id: str,
    objective: Callable[[dict[str, Any]], float],
    *,
    trials: int,
    timeout_seconds: int | None = None,
    sampler: str = "tpe",
    pruner: str = "median",
    seed: int = 42,
    jobs: int = 1,
) -> SearchResult:
    import optuna

    if sampler == "random":
        sampler_obj = optuna.samplers.RandomSampler(seed=seed)
    elif sampler == "cmaes":
        sampler_obj = optuna.samplers.CmaEsSampler(seed=seed)
    else:
        sampler_obj = optuna.samplers.TPESampler(seed=seed, multivariate=True)
    if pruner == "hyperband":
        pruner_obj = optuna.pruners.HyperbandPruner()
    elif pruner == "none":
        pruner_obj = optuna.pruners.NopPruner()
    else:
        pruner_obj = optuna.pruners.MedianPruner()
    study = optuna.create_study(direction="maximize", sampler=sampler_obj, pruner=pruner_obj)
    space = PARAM_SPACES.get(model_id, {})

    def wrapped(trial):
        return objective(_suggest_optuna(trial, space))

    study.optimize(
        wrapped, n_trials=trials, timeout=timeout_seconds, n_jobs=jobs, catch=(Exception,)
    )
    rows = [
        {"number": t.number, "value": t.value, "state": t.state.name, "params": t.params}
        for t in study.trials
    ]
    return SearchResult(study.best_params, float(study.best_value), rows, "optuna")


def _ray_space(space: dict[str, tuple]):
    from ray import tune

    result = {}
    for name, spec in space.items():
        kind = spec[0]
        if kind == "int":
            result[name] = tune.qrandint(spec[1], spec[2] + spec[3], spec[3])
        elif kind == "float":
            result[name] = tune.uniform(spec[1], spec[2])
        elif kind == "float_log":
            result[name] = tune.loguniform(spec[1], spec[2])
        elif kind == "categorical":
            result[name] = tune.choice(spec[1])
    return result


def optimize_ray(
    model_id: str,
    objective: Callable[[dict[str, Any]], float],
    *,
    trials: int,
    timeout_seconds: int | None = None,
    cpus_per_trial: float = 1.0,
    gpus_per_trial: float = 0.0,
    output_dir: str | None = None,
) -> SearchResult:
    from ray import tune

    space = _ray_space(PARAM_SPACES.get(model_id, {}))

    def trainable(config):
        tune.report({"score": objective(config)})

    tuner = tune.Tuner(
        tune.with_resources(trainable, {"cpu": cpus_per_trial, "gpu": gpus_per_trial}),
        param_space=space,
        tune_config=tune.TuneConfig(num_samples=trials, metric="score", mode="max"),
        run_config=tune.RunConfig(
            storage_path=output_dir,
            stop={"time_total_s": timeout_seconds} if timeout_seconds else None,
        ),
    )
    results = tuner.fit()
    best = results.get_best_result(metric="score", mode="max")
    rows = [
        {
            "config": result.config,
            "score": result.metrics.get("score"),
            "error": str(result.error) if result.error else None,
        }
        for result in results
    ]
    return SearchResult(dict(best.config), float(best.metrics["score"]), rows, "ray")
