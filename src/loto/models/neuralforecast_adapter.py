"""Validated planning layer for NeuralForecast AutoModels.

Plan resolution is dependency-light. Heavy optional imports occur only when an
actual model is constructed, allowing catalog and configuration tests on CPU-only
hosts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SUPPORTED_BACKENDS = {"optuna", "ray"}
MODELS_REQUIRING_N_SERIES = {
    "AutoTSMixer",
    "AutoTSMixerx",
    "AutoTimeMixer",
    "AutoRMoK",
    "AutoSOFTS",
    "AutoSOFTSSharp",
    "AutoXLinear",
    "AutoStemGNN",
    "AutoMLPMultivariate",
    "AutoiTransformer",
    "AutoTimeXer",
}
FFT_MODELS = {"AutoTimesNet", "AutoFEDformer"}


@dataclass(frozen=True)
class AutoModelRequest:
    model_name: str
    h: int
    config: dict[str, Any] | None = None
    backend: Literal["optuna", "ray"] | None = None
    cpus: int = 4
    gpus: int = 0
    parallel_trials: int = 1
    num_samples: int = 10
    refit_with_val: bool = False
    precision: str = "32-true"
    early_stop_patience_steps: int | None = None
    n_series: int | None = None
    random_seed: int = 42
    search_strategy: Literal["auto", "random", "tpe", "cmaes"] = "auto"


@dataclass(frozen=True)
class AutoModelPlan:
    model_name: str
    backend: str
    config: dict[str, Any]
    constructor_kwargs: dict[str, Any]
    precision: str
    adjustments: tuple[str, ...] = field(default_factory=tuple)
    search_algorithm: str = "library_default"


def choose_backend(*, gpus: int, cpus: int, requested: str | None, parallel_trials: int = 1) -> str:
    if requested is not None:
        if requested not in SUPPORTED_BACKENDS:
            raise ValueError(f"unsupported backend: {requested}")
        return requested
    if gpus == 0 and parallel_trials >= 4 and cpus >= parallel_trials:
        return "ray"
    return "optuna"


def _build_search_algorithm(backend: str, strategy: str, *, seed: int, num_samples: int):
    """Return ``(sampler_or_None, stable_name)``.

    Constitution principle II: the previous implementation wrapped the whole body in
    ``except Exception: return None, "library_default"``. That swallowed genuine bugs
    (a typo in a sampler name, a version incompatibility, a bad seed type) and reported them
    as an intentional fallback, and it made the test suite's verdict depend on whether optuna
    happened to be installed.

    Only ``ImportError`` is a legitimate fallback -- it means the optional package is absent,
    which is a declared state. Every other exception propagates.
    """
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"unsupported backend: {backend}")
    if strategy not in ("auto", "random", "tpe", "cmaes"):
        raise ValueError(f"unsupported search strategy: {strategy}")

    if backend == "optuna":
        try:
            import optuna
        except ImportError:
            return None, "library_default(optuna_absent)"
        selected = strategy
        if selected == "auto":
            selected = "random" if num_samples < 10 else "tpe"
        if selected == "random":
            return optuna.samplers.RandomSampler(seed=seed), "RandomSampler"
        if selected == "cmaes":
            return optuna.samplers.CmaEsSampler(seed=seed), "CmaEsSampler"
        return (
            optuna.samplers.TPESampler(seed=seed, multivariate=True),
            "TPESampler(multivariate=True)",
        )

    if num_samples < 10 or strategy == "random":
        try:
            from ray.tune.search.basic_variant import BasicVariantGenerator
        except ImportError:
            return None, "library_default(ray_absent)"
        return BasicVariantGenerator(random_state=seed), "BasicVariantGenerator"
    try:
        from ray.tune.search.optuna import OptunaSearch
    except ImportError:
        return None, "library_default(ray_absent)"
    return OptunaSearch(seed=seed), "Ray OptunaSearch"


def resolve_auto_model_plan(request: AutoModelRequest) -> AutoModelPlan:
    if request.h < 1:
        raise ValueError("h must be >= 1")
    if request.model_name in MODELS_REQUIRING_N_SERIES and request.n_series is None:
        raise ValueError(f"{request.model_name} requires n_series")
    backend = choose_backend(
        gpus=request.gpus,
        cpus=request.cpus,
        requested=request.backend,
        parallel_trials=request.parallel_trials,
    )
    config = dict(request.config or {})
    adjustments: list[str] = []
    for key in ("num_workers_loader", "num_workers"):
        if key in config:
            config.pop(key)
            adjustments.append(f"removed_unsupported_{key}")
    if request.early_stop_patience_steps is not None:
        config["early_stop_patience_steps"] = int(request.early_stop_patience_steps)
    precision = request.precision
    if request.model_name in FFT_MODELS and precision in {"16", "16-mixed", "bf16", "bf16-mixed"}:
        precision = "32-true"
        adjustments.append("precision_adjusted_for_fft")
    search_alg, search_name = _build_search_algorithm(
        backend, request.search_strategy, seed=request.random_seed, num_samples=request.num_samples
    )
    constructor_kwargs: dict[str, Any] = {
        "h": request.h,
        "config": None,
        "backend": backend,
        "num_samples": request.num_samples,
        "refit_with_val": request.refit_with_val,
        # neuralforecast >= 3.2.0 removed the legacy cpus/gpus
        # constructor arguments. Optuna runs in-process, so these values
        # must not be forwarded to AutoModel constructors.
        "verbose": True,
        "alias": f"{request.model_name}-{backend}",
    }
    needs_n_series = request.model_name in MODELS_REQUIRING_N_SERIES
    if needs_n_series and request.n_series is not None:
        config["n_series"] = int(request.n_series)
    if needs_n_series and request.n_series is not None:
        constructor_kwargs["n_series"] = int(request.n_series)
    # Empty config intentionally delegates to the official per-model default search space.
    if config:
        if backend == "optuna":
            frozen_config = dict(config)
            constructor_kwargs["config"] = lambda _trial, c=frozen_config: dict(c)
            adjustments.append("fixed_optuna_config")
        else:
            constructor_kwargs["config"] = config
    if search_alg is not None:
        constructor_kwargs["search_alg"] = search_alg
    return AutoModelPlan(
        request.model_name,
        backend,
        config,
        constructor_kwargs,
        precision,
        tuple(adjustments),
        search_name,
    )


def construct_auto_model(plan: AutoModelPlan):
    try:
        import neuralforecast.auto as nf_auto
    except ImportError as exc:
        raise RuntimeError("neuralforecast is not installed; install the full extra") from exc
    cls = getattr(nf_auto, plan.model_name, None)
    if cls is None:
        raise ValueError(f"NeuralForecast does not expose {plan.model_name}")
    return cls(**plan.constructor_kwargs)
