from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any

from .contracts import (
    ArchitectureProfile,
    PinnedLLMIdentity,
    TrialParameters,
    load_snapshot_model_metadata,
    resolve_architecture,
    verify_snapshot,
)

_RUNTIME_LOCK = RLock()
_RUNTIME_CLASSES: tuple[type[Any], type[Any]] | None = None
_REQUIRED_MODULES = ("neuralforecast", "ray", "transformers")

PinnedTimeLLM: type[Any]
AutoTimeLLM: type[Any]


class RuntimeDependencyError(RuntimeError):
    pass


def runtime_dependency_status() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in _REQUIRED_MODULES}


def _load_runtime_dependencies() -> dict[str, Any]:
    status = runtime_dependency_status()
    missing = sorted(name for name, available in status.items() if not available)
    if missing:
        raise RuntimeDependencyError(
            "AutoTimeLLM runtime dependencies are unavailable: " + ", ".join(missing)
        )

    from neuralforecast.common._base_auto import BaseAuto
    from neuralforecast.losses import pytorch as losses
    from neuralforecast.models.timellm import TimeLLM
    from ray import tune
    from ray.tune.search.basic_variant import BasicVariantGenerator

    return {
        "BaseAuto": BaseAuto,
        "losses": losses,
        "TimeLLM": TimeLLM,
        "tune": tune,
        "BasicVariantGenerator": BasicVariantGenerator,
    }


@contextmanager
def _offline_environment() -> Iterator[None]:
    values = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
    }
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _inject_identity(
    config: Any,
    *,
    backend: str,
    identity: PinnedLLMIdentity,
) -> Any:
    payload = identity.model_dump(mode="json")
    if backend == "ray":
        if not isinstance(config, dict):
            raise TypeError("Ray AutoTimeLLM config must be a dictionary")
        return {**config, "llm_identity": payload}
    if backend == "optuna":
        if not callable(config):
            raise TypeError("Optuna AutoTimeLLM config must be callable")

        def wrapped(trial: Any) -> dict[str, Any]:
            resolved = config(trial)
            if not isinstance(resolved, dict):
                raise TypeError("Optuna AutoTimeLLM config did not return a dictionary")
            return {**resolved, "llm_identity": payload}

        return wrapped
    raise ValueError(f"unsupported AutoTimeLLM backend: {backend}")


def _loaded_snapshot_names(model: Any) -> dict[str, str | None]:
    config_name = getattr(getattr(model, "llm_config", None), "_name_or_path", None)
    llm = getattr(model, "llm", None)
    llm_name = getattr(llm, "name_or_path", None)
    if llm_name is None:
        llm_name = getattr(getattr(llm, "config", None), "_name_or_path", None)
    tokenizer_name = getattr(getattr(model, "llm_tokenizer", None), "name_or_path", None)
    return {
        "config": config_name if isinstance(config_name, str) else None,
        "model": llm_name if isinstance(llm_name, str) else None,
        "tokenizer": tokenizer_name if isinstance(tokenizer_name, str) else None,
    }


def _require_loaded_snapshot(model: Any, expected_snapshot: Path) -> dict[str, str]:
    observed = _loaded_snapshot_names(model)
    normalized: dict[str, str] = {}
    for component, value in observed.items():
        if value is None:
            raise RuntimeError(f"loaded {component} identity is unavailable")
        path = Path(value)
        if not path.is_absolute() or path.resolve() != expected_snapshot:
            raise RuntimeError(
                f"loaded {component} identity does not match the pinned local snapshot"
            )
        normalized[component] = str(path.resolve())
    return normalized


def _build_runtime_classes() -> tuple[type[Any], type[Any]]:
    global _RUNTIME_CLASSES
    with _RUNTIME_LOCK:
        if _RUNTIME_CLASSES is not None:
            return _RUNTIME_CLASSES

        deps = _load_runtime_dependencies()
        BaseAuto = deps["BaseAuto"]
        losses = deps["losses"]
        TimeLLM = deps["TimeLLM"]
        tune = deps["tune"]
        BasicVariantGenerator = deps["BasicVariantGenerator"]

        class PinnedTimeLLM(TimeLLM):
            EXOGENOUS_FUTR = False
            EXOGENOUS_HIST = False
            EXOGENOUS_STAT = False
            MULTIVARIATE = False
            RECURRENT = False

            def __init__(
                self,
                h: int,
                architecture_profile: str,
                llm_identity: dict[str, Any],
                loss: Any = None,
                valid_loss: Any = None,
                learning_rate: float = 1e-4,
                max_steps: int = 100,
                val_check_steps: int = 20,
                batch_size: int = 16,
                windows_batch_size: int = 64,
                dropout: float = 0.1,
                scaler_type: str = "identity",
                random_seed: int = 1,
                **trainer_kwargs: Any,
            ) -> None:
                if loss is None:
                    loss = losses.MAE()
                identity = PinnedLLMIdentity.model_validate(llm_identity)
                verification = verify_snapshot(identity)
                metadata = load_snapshot_model_metadata(identity)
                trial = TrialParameters(
                    architecture_profile=ArchitectureProfile(architecture_profile),
                    learning_rate=learning_rate,
                    max_steps=max_steps,
                    val_check_steps=val_check_steps,
                    batch_size=batch_size,
                    windows_batch_size=windows_batch_size,
                    dropout=dropout,
                    scaler_type=scaler_type,
                    random_seed=random_seed,
                )
                architecture = resolve_architecture(h, trial.architecture_profile)
                if architecture.d_ff > metadata.hidden_size:
                    raise ValueError("d_ff must not exceed the pinned LLM hidden size")
                if getattr(loss, "outputsize_multiplier", 1) != 1:
                    raise ValueError("AutoTimeLLM supports point training losses only")
                base_point_loss = getattr(losses, "BasePointLoss", ())
                if valid_loss is not None and not isinstance(valid_loss, base_point_loss):
                    raise ValueError("AutoTimeLLM supports point validation losses only")

                snapshot = Path(verification.snapshot_path)
                with _offline_environment():
                    super().__init__(
                        h=h,
                        input_size=architecture.input_size,
                        patch_len=architecture.patch_len,
                        stride=architecture.stride,
                        d_ff=architecture.d_ff,
                        top_k=architecture.top_k,
                        d_llm=metadata.hidden_size,
                        d_model=architecture.d_model,
                        n_heads=architecture.n_heads,
                        enc_in=1,
                        dec_in=1,
                        llm=str(snapshot),
                        llm_num_hidden_layers=metadata.num_hidden_layers,
                        dropout=trial.dropout,
                        loss=loss,
                        valid_loss=valid_loss,
                        learning_rate=trial.learning_rate,
                        max_steps=trial.max_steps,
                        val_check_steps=trial.val_check_steps,
                        batch_size=trial.batch_size,
                        windows_batch_size=trial.windows_batch_size,
                        scaler_type=trial.scaler_type,
                        random_seed=trial.random_seed,
                        **trainer_kwargs,
                    )

                loaded = _require_loaded_snapshot(self, snapshot)
                self.loto_model_id = "nf-local-auto-timellm"
                self.loto_llm_identity = identity.model_dump(mode="json")
                self.loto_snapshot_verification = verification.model_dump(mode="json")
                self.loto_architecture = architecture.model_dump(mode="json")
                self.loto_loaded_snapshot_identity = loaded
                self.loto_cpu_fallback = False

        class AutoTimeLLM(BaseAuto):
            default_profiles = tuple(profile.value for profile in ArchitectureProfile)

            def __init__(
                self,
                h: int,
                llm_identity: PinnedLLMIdentity | dict[str, Any],
                loss: Any = None,
                valid_loss: Any = None,
                config: Any = None,
                search_alg: Any = None,
                num_samples: int = 10,
                time_budget: int | None = None,
                refit_with_val: bool = False,
                cpus: int | None = None,
                gpus: int | float | None = None,
                verbose: bool = False,
                alias: str | None = None,
                backend: str = "ray",
                callbacks: list[Any] | None = None,
                ray_options: Any = None,
                optuna_options: Any = None,
            ) -> None:
                if loss is None:
                    loss = losses.MAE()
                identity = PinnedLLMIdentity.model_validate(llm_identity)
                if config is None:
                    config = self.get_default_config(h=h, backend=backend)
                config = _inject_identity(config, backend=backend, identity=identity)
                if search_alg is None:
                    search_alg = BasicVariantGenerator(random_state=1)
                super().__init__(
                    cls_model=PinnedTimeLLM,
                    h=h,
                    loss=loss,
                    valid_loss=valid_loss,
                    config=config,
                    search_alg=search_alg,
                    num_samples=num_samples,
                    time_budget=time_budget,
                    refit_with_val=refit_with_val,
                    cpus=cpus,
                    gpus=gpus,
                    verbose=verbose,
                    alias=alias,
                    backend=backend,
                    callbacks=callbacks,
                    ray_options=ray_options,
                    optuna_options=optuna_options,
                )
                self.loto_model_id = "nf-local-auto-timellm"
                self.loto_llm_identity = identity.model_dump(mode="json")

            @classmethod
            def get_default_config(
                cls,
                h: int,
                backend: str,
                n_series: int | None = None,
            ) -> Any:
                del n_series
                if not isinstance(h, int) or isinstance(h, bool) or h < 1:
                    raise ValueError("h must be a positive integer")
                config: dict[str, Any] = {
                    "h": None,
                    "architecture_profile": tune.choice(list(cls.default_profiles)),
                    "learning_rate": tune.loguniform(1e-5, 1e-3),
                    "max_steps": tune.choice([100, 300, 500]),
                    "val_check_steps": tune.choice([20, 50, 100]),
                    "batch_size": tune.choice([8, 16, 32]),
                    "windows_batch_size": tune.choice([32, 64, 128]),
                    "dropout": tune.choice([0.0, 0.1, 0.2]),
                    "scaler_type": tune.choice(["identity", "robust"]),
                    "random_seed": tune.randint(1, 20),
                }
                if backend == "optuna":
                    return cls._ray_config_to_optuna(config)
                if backend != "ray":
                    raise ValueError(f"unsupported AutoTimeLLM backend: {backend}")
                return config

        PinnedTimeLLM.__name__ = "PinnedTimeLLM"
        PinnedTimeLLM.__qualname__ = "PinnedTimeLLM"
        PinnedTimeLLM.__module__ = __name__
        AutoTimeLLM.__name__ = "AutoTimeLLM"
        AutoTimeLLM.__qualname__ = "AutoTimeLLM"
        AutoTimeLLM.__module__ = __name__
        globals()["PinnedTimeLLM"] = PinnedTimeLLM
        globals()["AutoTimeLLM"] = AutoTimeLLM
        _RUNTIME_CLASSES = (PinnedTimeLLM, AutoTimeLLM)
        return _RUNTIME_CLASSES


def get_pinned_timellm_class() -> type[Any]:
    return _build_runtime_classes()[0]


def get_auto_timellm_class() -> type[Any]:
    return _build_runtime_classes()[1]


def construct_auto_timellm(**kwargs: Any) -> Any:
    return get_auto_timellm_class()(**kwargs)


def __getattr__(name: str) -> Any:
    if name == "PinnedTimeLLM":
        return get_pinned_timellm_class()
    if name == "AutoTimeLLM":
        return get_auto_timellm_class()
    raise AttributeError(name)


def _reset_runtime_classes_for_tests() -> None:
    global _RUNTIME_CLASSES
    with _RUNTIME_LOCK:
        _RUNTIME_CLASSES = None
        globals().pop("PinnedTimeLLM", None)
        globals().pop("AutoTimeLLM", None)


__all__ = [
    "AutoTimeLLM",
    "PinnedTimeLLM",
    "RuntimeDependencyError",
    "construct_auto_timellm",
    "get_auto_timellm_class",
    "get_pinned_timellm_class",
    "runtime_dependency_status",
]
