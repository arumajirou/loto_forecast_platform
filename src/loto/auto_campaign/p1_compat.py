from __future__ import annotations

import copy
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import torch

ConfigProvider = dict[str, Any] | Callable[[Any], dict[str, Any]]
T = TypeVar("T")


_DECODER_MODELS = {
    "Autoformer",
    "FEDformer",
    "Informer",
    "TimeMixer",
    "VanillaTransformer",
}


def _deduplicate(values: list[T]) -> list[T]:
    result: list[T] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _map_search_value(
    value: Any,
    transform: Callable[[Any], Any],
) -> Any:
    categories = getattr(value, "categories", None)
    if categories is None:
        return transform(value)

    from ray import tune

    transformed = _deduplicate([transform(item) for item in categories])
    return tune.choice(transformed)


def _minimum_int(value: Any, minimum: int) -> Any:
    def transform(item: Any) -> Any:
        if isinstance(item, bool):
            return item
        if isinstance(item, (int, float)):
            return max(minimum, int(item))
        return item

    return _map_search_value(value, transform)


def _canonical_model_name(name: str) -> str:
    while name.startswith("Persistent"):
        name = name.removeprefix("Persistent")
    if name.startswith("AutoAuto"):
        return name.removeprefix("Auto")
    if name in {"AutoiTransformer", "AutoxLSTM"}:
        return name.removeprefix("Auto")
    if name.startswith("Auto") and name not in _DECODER_MODELS:
        return name.removeprefix("Auto")
    return name


def sanitize_model_config(
    config: dict[str, Any],
    *,
    model_name: str,
) -> dict[str, Any]:
    """Return an audit-ready model config before search and hashing."""
    normalized = copy.deepcopy(config)
    model_name = _canonical_model_name(model_name)
    horizon = int(normalized.get("h", 1) or 1)

    if "deterministic" in normalized:
        normalized["deterministic"] = _map_search_value(
            normalized["deterministic"],
            lambda value: "warn" if value is True else value,
        )

    trainer_kwargs = normalized.get("trainer_kwargs")
    if isinstance(trainer_kwargs, dict):
        trainer_kwargs = copy.deepcopy(trainer_kwargs)
        if "deterministic" in trainer_kwargs:
            trainer_kwargs["deterministic"] = _map_search_value(
                trainer_kwargs["deterministic"],
                lambda value: "warn" if value is True else value,
            )
        normalized["trainer_kwargs"] = trainer_kwargs

    if horizon == 1 and model_name in _DECODER_MODELS:
        normalized["input_size"] = _minimum_int(
            normalized.get("input_size", 1),
            2,
        )

    if horizon == 1 and model_name == "BiTCN":
        normalized["input_size"] = _minimum_int(
            normalized.get("input_size", 1),
            2,
        )

    if horizon == 1 and model_name in {"NBEATS", "NBEATSx"}:
        normalized["stack_types"] = ["identity"]
        normalized["n_blocks"] = [1]
        normalized["mlp_units"] = [[64, 64]]

    if horizon == 1 and model_name == "TimesNet":
        normalized["input_size"] = _minimum_int(
            normalized.get("input_size", 1),
            4,
        )
        normalized["top_k"] = 1

    if horizon == 1 and model_name == "TimeXer":
        patch_len = normalized.get("patch_len", 16)
        if isinstance(patch_len, (int, float)):
            minimum = max(2, int(patch_len))
        else:
            minimum = 16
        normalized["input_size"] = _minimum_int(
            normalized.get("input_size", 1),
            minimum,
        )

    return normalized


def _wrap_config_provider(
    provider: ConfigProvider,
    *,
    model_name: str,
) -> ConfigProvider:
    if isinstance(provider, dict):
        return sanitize_model_config(
            provider,
            model_name=model_name,
        )

    wrapped_marker = getattr(
        provider,
        "_p1_v12_model_name",
        None,
    )
    if wrapped_marker == model_name:
        return provider

    def wrapped(trial: Any) -> dict[str, Any]:
        return sanitize_model_config(
            provider(trial),
            model_name=model_name,
        )

    wrapped_any: Any = wrapped
    wrapped_any._p1_v12_model_name = model_name
    wrapped_any._p1_v12_original = provider
    return wrapped


def prepare_auto_model_config(
    auto_model: Any,
    requested_config: Any,
    *,
    model_name: str | None = None,
) -> Any:
    """Apply compatibility fixes before fit, trial persistence and auditing."""
    cls_model = getattr(auto_model, "cls_model", None)
    resolved_name = getattr(cls_model, "__name__", None) or model_name or type(auto_model).__name__
    resolved_name = _canonical_model_name(str(resolved_name))

    provider = getattr(auto_model, "config", None)
    if isinstance(provider, dict) or callable(provider):
        auto_model.config = _wrap_config_provider(
            provider,
            model_name=resolved_name,
        )

    if isinstance(requested_config, dict) or callable(requested_config):
        return _wrap_config_provider(
            requested_config,
            model_name=resolved_name,
        )

    return requested_config


def install_p1_runtime_compatibility() -> None:
    """Configure runtime without changing a config after it was frozen."""
    torch.set_float32_matmul_precision("high")
    torch.use_deterministic_algorithms(
        True,
        warn_only=True,
    )
    warnings.filterwarnings(
        "default",
        category=DeprecationWarning,
    )


def _persistent_auto_base(cls: type) -> type | None:
    return next(
        (candidate for candidate in cls.__mro__[1:] if candidate.__name__.startswith("Auto")),
        None,
    )


def normalize_persistent_auto_class_names(
    neural_forecast: Any,
) -> list[dict[str, str]]:
    """Permanently normalize dynamic class names; kept for compatibility."""
    changes: list[dict[str, str]] = []

    for model in getattr(neural_forecast, "models", []):
        cls = type(model)
        old_name = cls.__name__
        if not old_name.startswith("PersistentAuto"):
            continue

        base = _persistent_auto_base(cls)
        if base is None:
            continue

        cls.__name__ = base.__name__
        cls.__qualname__ = base.__qualname__
        changes.append(
            {
                "from": old_name,
                "to": base.__name__,
            }
        )

    return changes


def save_neuralforecast_compat(
    neural_forecast: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Save PersistentAuto models using names recognized by NeuralForecast."""
    changes: list[tuple[type, str, str]] = []

    for model in getattr(neural_forecast, "models", []):
        cls = type(model)
        if not cls.__name__.startswith("PersistentAuto"):
            continue

        base = _persistent_auto_base(cls)
        if base is None:
            continue

        changes.append(
            (
                cls,
                cls.__name__,
                cls.__qualname__,
            )
        )
        cls.__name__ = base.__name__
        cls.__qualname__ = base.__qualname__

    try:
        return neural_forecast.save(
            *args,
            **kwargs,
        )
    finally:
        for cls, name, qualname in reversed(changes):
            cls.__name__ = name
            cls.__qualname__ = qualname


def _lightning_version() -> str:
    try:
        import lightning.pytorch as pl

        return str(pl.__version__)
    except ImportError:
        import pytorch_lightning as pl

        return str(pl.__version__)


def save_trial_checkpoint(
    *,
    model: Any,
    checkpoint_path: str | Path,
    fallback_payload: dict[str, Any],
) -> None:
    """Write a genuine Trainer checkpoint when possible, else a compatible one."""
    path = Path(checkpoint_path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    trainer = getattr(model, "trainer", None)
    if trainer is not None and hasattr(
        trainer,
        "save_checkpoint",
    ):
        try:
            trainer.save_checkpoint(
                str(path),
                weights_only=False,
            )
        except TypeError:
            trainer.save_checkpoint(str(path))

    if path.is_file():
        payload = torch.load(
            path,
            map_location="cpu",
            weights_only=False,
        )
    else:
        payload = copy.deepcopy(fallback_payload)

    if not isinstance(payload, dict):
        raise TypeError("checkpoint payload must be a dictionary")

    payload.setdefault(
        "pytorch-lightning_version",
        _lightning_version(),
    )
    payload.setdefault("epoch", 0)
    payload.setdefault("global_step", 0)
    payload.setdefault("callbacks", {})
    payload.setdefault("optimizer_states", [])
    payload.setdefault("lr_schedulers", [])

    if "state_dict" not in payload:
        payload["state_dict"] = model.state_dict()

    torch.save(payload, path)


def load_trial_checkpoint_for_verification(
    *,
    model: Any,
    checkpoint_path: str | Path,
) -> Any:
    """Load a trial checkpoint, with a strict state_dict fallback."""
    path = Path(checkpoint_path)
    payload = torch.load(
        path,
        map_location="cpu",
        weights_only=False,
    )

    if not isinstance(payload, dict):
        raise TypeError("checkpoint payload must be a dictionary")

    if "pytorch-lightning_version" in payload:
        try:
            loaded = type(model).load_from_checkpoint(
                str(path),
                map_location="cpu",
            )
            loaded._p1_checkpoint_load_mode = "lightning"
            return loaded
        except Exception:
            pass

    state_dict = payload.get("state_dict")
    if not isinstance(state_dict, dict):
        raise KeyError("checkpoint has no state_dict")

    loaded = copy.deepcopy(model).cpu()
    loaded.load_state_dict(
        state_dict,
        strict=True,
    )
    loaded._p1_checkpoint_load_mode = "state_dict"
    return loaded
