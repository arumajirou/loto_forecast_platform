from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loto.models.neuralforecast_search_policy import (
    SearchAlgorithmMaterialization,
    SearchPolicyDecision,
    instantiate_search_algorithm,
    resolve_search_policy,
)
from loto.models.neuralforecast_search_space import (
    SearchSpaceProfile,
    profile_fixed_config,
    profile_optuna_config,
    profile_ray_config,
)
from loto.models.neuralforecast_search_space_artifacts import persist_search_space_artifacts

from .contracts import CampaignConfig
from .data_tracks import hint_summing_matrix
from .domains import freeze_config
from .registry import get_auto_class, get_default_config
from .trial_persistence import persistent_auto_class


def _search_space_evidence_root(trial_root: Path) -> Path:
    """Return a task-key-specific evidence directory that survives task failure."""

    resolved = trial_root.resolve()
    for parent in (resolved, *resolved.parents):
        if parent.name == "trial_work":
            relative = resolved.relative_to(parent)
            return parent.parent / "search_space_profiles" / relative
    return resolved / "search_space_profile"


def _search_space_profile(
    *,
    model_name: str,
    backend: str,
    config_value: Any,
    fixed_values: dict[str, Any] | None,
) -> SearchSpaceProfile:
    if fixed_values is not None:
        return profile_fixed_config(fixed_values, backend=backend, model_name=model_name)
    if backend == "ray":
        if not isinstance(config_value, dict):
            raise TypeError("Ray search-space profile requires a dict config")
        return profile_ray_config(config_value, model_name=model_name)
    if not callable(config_value):
        raise TypeError("Optuna search-space profile requires a callable config")
    return profile_optuna_config(config_value, model_name=model_name)


def _persist_search_space_profile(
    *,
    trial_root: Path,
    profile: SearchSpaceProfile,
    model_name: str,
    backend: str,
    alias: str,
    seed: int,
    num_samples: int,
    smoke: bool,
) -> dict[str, Any]:
    return persist_search_space_artifacts(
        _search_space_evidence_root(trial_root),
        profile,
        context={
            "model_name": model_name,
            "backend": backend,
            "alias": alias,
            "seed": seed,
            "num_samples": num_samples,
            "smoke": smoke,
            "trial_root": str(trial_root),
        },
    )


def _ray_options(config: CampaignConfig):
    from neuralforecast.common._base_auto import RayOptions
    from ray import tune

    return RayOptions(
        run_config=tune.RunConfig(callbacks=None, verbose=1),
        cpus=config.resources.cpus_per_trial,
        gpus=config.resources.gpus_per_trial,
    )


def _optuna_options():
    from neuralforecast.common._base_auto import OptunaOptions

    return OptunaOptions(
        create_study_kwargs={},
        study_kwargs={"gc_after_trial": True},
    )


def _fixed_optuna_config(values: dict[str, Any]) -> Callable[[Any], dict[str, Any]]:
    snapshot = dict(values)

    def config_fn(_trial: Any) -> dict[str, Any]:
        return dict(snapshot)

    return config_fn


def _search_materialization(
    *,
    config: CampaignConfig,
    backend: str,
    model_name: str,
    num_samples: int,
) -> SearchAlgorithmMaterialization:
    decision = resolve_search_policy(
        backend=backend,
        strategy=config.search.strategy,
        search_seed=config.search.search_seed,
        num_samples=num_samples,
        model_name=model_name,
    )
    return instantiate_search_algorithm(
        decision,
        allow_fallback=config.search.allow_fallback,
    )


def _trainer_controls(config: CampaignConfig, *, seed: int) -> dict[str, Any]:
    return {
        "accelerator": config.resources.accelerator,
        "devices": config.resources.devices,
        "precision": config.resources.precision,
        "enable_checkpointing": False,
        "enable_progress_bar": False,
        "logger": False,
        "deterministic": True,
        "benchmark": False,
        "num_sanity_val_steps": 0,
        "random_seed": seed,
    }


def _augment_search_config(
    value: Any,
    *,
    backend: str,
    controls: dict[str, Any],
) -> Any:
    if backend == "ray":
        if not isinstance(value, dict):
            raise TypeError("Ray AutoModel config must be a dict")
        return {**value, **controls}

    if not callable(value):
        raise TypeError("Optuna AutoModel config must be callable")

    def wrapped(trial: Any) -> dict[str, Any]:
        resolved = value(trial)
        if not isinstance(resolved, dict):
            raise TypeError("Optuna config callable did not return a dict")
        return {**resolved, **controls}

    return wrapped


def _common_kwargs(
    *,
    config: CampaignConfig,
    backend: str,
    model_name: str,
    alias: str,
    config_value: Any,
    num_samples: int,
) -> tuple[dict[str, Any], SearchPolicyDecision]:
    from neuralforecast.common._base_auto import OptunaOptions, RayOptions

    materialized = _search_materialization(
        config=config,
        backend=backend,
        model_name=model_name,
        num_samples=num_samples,
    )
    kwargs: dict[str, Any] = {
        "h": config.h,
        "config": config_value,
        "num_samples": num_samples,
        "time_budget": config.search.time_budget,
        "refit_with_val": config.search.refit_with_val,
        "verbose": config.search.verbose,
        "alias": alias,
        "backend": backend,
        "callbacks": None,
        "ray_options": _ray_options(config) if backend == "ray" else RayOptions(),
        "optuna_options": _optuna_options() if backend == "optuna" else OptunaOptions(),
        "cpus": None,
        "gpus": None,
    }
    if materialized.algorithm is not None:
        kwargs["search_alg"] = materialized.algorithm
    kwargs.update(config.extra_base_auto_args)
    if kwargs.get("cpus") is not None or kwargs.get("gpus") is not None:
        raise ValueError("NeuralForecast 3.2.0 rejects direct cpus/gpus; use resources/RayOptions")
    return kwargs, materialized.decision


def _constructor_argument_decisions(
    cls: type,
    kwargs: dict[str, Any],
    *,
    strict_keys: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    signature = inspect.signature(cls)
    accepts_var_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    accepted_names = set(signature.parameters)
    effective: dict[str, Any] = {}
    ledger: list[dict[str, Any]] = []
    rejected: list[str] = []
    for key, value in kwargs.items():
        if key in accepted_names or accepts_var_kwargs:
            effective[key] = value
            status = "ACCEPTED"
            reason = "constructor signature accepts argument"
        elif key in strict_keys:
            status = "REJECTED"
            reason = "explicit extra_base_auto_args key is absent from constructor signature"
            rejected.append(key)
        elif key in {"cpus", "gpus"}:
            status = "UNSUPPORTED_BY_VERSION"
            reason = "NeuralForecast 3.2.0 requires RayOptions instead of direct resources"
        else:
            status = "NOT_APPLICABLE"
            reason = "model-specific constructor does not expose this common BaseAuto argument"
        ledger.append(
            {
                "argument": key,
                "status": status,
                "reason": reason,
                "value_repr": repr(value),
            }
        )
    if rejected:
        raise ValueError(f"constructor rejected explicit arguments for {cls.__name__}: {rejected}")
    return effective, ledger


def _artifact_kwargs(
    effective_kwargs: dict[str, Any],
    ledger: list[dict[str, Any]],
    search_policy: SearchPolicyDecision | None = None,
    *,
    search_space_profile: SearchSpaceProfile | None = None,
    search_space_artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = dict(effective_kwargs)
    artifact.update(
        {
            "effective_constructor_kwargs": effective_kwargs,
            "argument_coverage": ledger,
            "unexplained_dropped_arguments": [
                row["argument"] for row in ledger if row["status"] == "DROPPED"
            ],
            "search_policy": (
                search_policy.model_dump(mode="json") if search_policy is not None else None
            ),
            "search_space_profile": (
                search_space_profile.model_dump(mode="json")
                if search_space_profile is not None
                else None
            ),
            "search_space_artifacts": search_space_artifacts,
        }
    )
    return artifact


def _hint_model(
    *,
    config: CampaignConfig,
    backend: str,
    alias: str,
    trial_root: Path,
    num_samples: int,
    seed: int,
    smoke: bool,
    fixed_config: dict[str, Any] | None,
    preserve_fixed_random_seed: bool,
):
    if backend != "ray":
        raise ValueError("NeuralForecast 3.2.0 AutoHINT supports only backend='ray'")

    from neuralforecast.auto import AutoHINT
    from neuralforecast.losses.pytorch import GMM, sCRPS
    from neuralforecast.models import NHITS

    auto_cls = persistent_auto_class(AutoHINT)
    base_config: dict[str, Any] = {
        "learning_rate": 1e-3,
        "max_steps": config.max_steps_smoke if smoke else 500,
        "val_check_steps": config.val_check_steps_smoke if smoke else 50,
        "input_size": max(5, config.h * 5),
        "batch_size": 6,
        "windows_batch_size": 32 if smoke else 256,
        "n_pool_kernel_size": [1, 1, 1],
        "n_freq_downsample": [1, 1, 1],
        "activation": "ReLU",
        "n_blocks": [1, 1, 1],
        "mlp_units": [[32, 32], [32, 32], [32, 32]],
        "interpolation_mode": "linear",
        "reconciliation": "BottomUp",
        **_trainer_controls(config, seed=seed),
    }
    if fixed_config is not None:
        base_config.update(fixed_config)
        controls = _trainer_controls(config, seed=seed)
        if preserve_fixed_random_seed and "random_seed" in fixed_config:
            controls.pop("random_seed", None)
        base_config.update(controls)

    if fixed_config is None and not smoke:
        from ray import tune

        config_value: Any = {
            **base_config,
            "learning_rate": tune.loguniform(1e-4, 1e-2),
            "input_size": tune.choice([max(5, config.h * value) for value in (5, 10, 20)]),
            "max_steps": tune.choice([500, 1000]),
            "reconciliation": tune.choice(["BottomUp", "MinTraceOLS", "MinTraceWLS"]),
            "random_seed": tune.randint(1, 20),
        }
    else:
        config_value = base_config

    search_space_profile = _search_space_profile(
        model_name="AutoHINT",
        backend=backend,
        config_value=config_value,
        fixed_values=base_config if fixed_config is not None or smoke else None,
    )
    search_space_artifacts = _persist_search_space_profile(
        trial_root=trial_root,
        profile=search_space_profile,
        model_name="AutoHINT",
        backend=backend,
        alias=alias,
        seed=seed,
        num_samples=num_samples,
        smoke=smoke,
    )

    proposed_kwargs, search_policy = _common_kwargs(
        config=config,
        backend=backend,
        model_name="AutoHINT",
        alias=alias,
        config_value=config_value,
        num_samples=num_samples,
    )
    proposed_kwargs.update(
        {
            "cls_model": NHITS,
            "loss": GMM(n_components=2, level=[80, 90]),
            "valid_loss": sCRPS(level=[80, 90]),
            "S": hint_summing_matrix(5),
        }
    )
    kwargs, ledger = _constructor_argument_decisions(
        AutoHINT,
        proposed_kwargs,
        strict_keys=set(config.extra_base_auto_args),
    )
    model = auto_cls(**kwargs)
    model.trial_artifact_root = str(trial_root)
    model.argument_coverage = ledger
    model.search_policy_decision = search_policy.model_dump(mode="json")
    model.search_space_profile = search_space_profile.model_dump(mode="json")
    model.search_space_artifacts = search_space_artifacts
    return (
        model,
        config_value,
        _artifact_kwargs(
            kwargs,
            ledger,
            search_policy,
            search_space_profile=search_space_profile,
            search_space_artifacts=search_space_artifacts,
        ),
    )


def build_auto_model(
    *,
    model_name: str,
    config: CampaignConfig,
    backend: str,
    alias: str,
    trial_root: Path,
    n_series: int | None,
    num_samples: int,
    seed: int,
    smoke: bool,
    fixed_config: dict[str, Any] | None = None,
    preserve_fixed_random_seed: bool = False,
):
    if model_name == "AutoHINT":
        return _hint_model(
            config=config,
            backend=backend,
            alias=alias,
            trial_root=trial_root,
            num_samples=num_samples,
            seed=seed,
            smoke=smoke,
            fixed_config=fixed_config,
            preserve_fixed_random_seed=preserve_fixed_random_seed,
        )

    original_cls = get_auto_class(model_name)
    auto_cls = persistent_auto_class(original_cls)
    controls = _trainer_controls(config, seed=seed)

    if fixed_config is not None:
        if preserve_fixed_random_seed and "random_seed" in fixed_config:
            controls = {key: value for key, value in controls.items() if key != "random_seed"}
        requested = {**fixed_config, **controls}
        config_value: Any = _fixed_optuna_config(requested) if backend == "optuna" else requested
    elif smoke:
        default = get_default_config(
            model_name,
            h=config.h,
            backend="ray",
            n_series=n_series,
        )
        requested = freeze_config(
            default,
            strategy="small",
            h=config.h,
            n_series=n_series,
            seed=seed,
            smoke=True,
            max_steps_smoke=config.max_steps_smoke,
            val_check_steps_smoke=config.val_check_steps_smoke,
            accelerator=config.resources.accelerator,
            devices=config.resources.devices,
            precision=config.resources.precision,
        )
        config_value = _fixed_optuna_config(requested) if backend == "optuna" else requested
    else:
        official = get_default_config(
            model_name,
            h=config.h,
            backend=backend,
            n_series=n_series,
        )
        config_value = _augment_search_config(
            official,
            backend=backend,
            controls=controls,
        )
        requested = config_value

    fixed_values = (
        requested if isinstance(requested, dict) and (fixed_config is not None or smoke) else None
    )
    search_space_profile = _search_space_profile(
        model_name=model_name,
        backend=backend,
        config_value=config_value,
        fixed_values=fixed_values,
    )
    search_space_artifacts = _persist_search_space_profile(
        trial_root=trial_root,
        profile=search_space_profile,
        model_name=model_name,
        backend=backend,
        alias=alias,
        seed=seed,
        num_samples=num_samples,
        smoke=smoke,
    )

    signature = inspect.signature(original_cls)
    proposed_kwargs, search_policy = _common_kwargs(
        config=config,
        backend=backend,
        model_name=model_name,
        alias=alias,
        config_value=config_value,
        num_samples=num_samples,
    )
    if "n_series" in signature.parameters:
        if n_series is None:
            raise ValueError(f"{model_name} requires n_series")
        proposed_kwargs["n_series"] = n_series

    kwargs, ledger = _constructor_argument_decisions(
        original_cls,
        proposed_kwargs,
        strict_keys=set(config.extra_base_auto_args),
    )
    model = auto_cls(**kwargs)
    model.trial_artifact_root = str(trial_root)
    model.argument_coverage = ledger
    model.search_policy_decision = search_policy.model_dump(mode="json")
    model.search_space_profile = search_space_profile.model_dump(mode="json")
    model.search_space_artifacts = search_space_artifacts
    return (
        model,
        requested,
        _artifact_kwargs(
            kwargs,
            ledger,
            search_policy,
            search_space_profile=search_space_profile,
            search_space_artifacts=search_space_artifacts,
        ),
    )
