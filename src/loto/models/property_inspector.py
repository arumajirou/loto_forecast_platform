from __future__ import annotations

# ruff: noqa: E501
import importlib.metadata
from pathlib import Path
from typing import Any

from loto.models.artifact_store import artifact_summary
from loto.models.catalog import ModelSpec

PROPERTY_NAMES = (
    "model_id",
    "class_name",
    "library",
    "library_version",
    "task",
    "capabilities",
    "device",
    "dtype",
    "precision",
    "parameter_count",
    "trainable_parameter_count",
    "input_size",
    "horizon",
    "batch_size",
    "max_steps",
    "epochs",
    "learning_rate",
    "optimizer",
    "loss",
    "random_seed",
    "lags",
    "context_length",
    "hidden_size",
    "layers",
    "heads",
    "dropout",
    "n_series",
    "backend",
    "num_samples",
    "checkpoint_path",
    "model_file_path",
    "model_file_size",
    "model_sha256",
    "artifact_type",
    "artifact_file_count",
    "fit_supported",
    "refit_supported",
    "incremental_supported",
    "save_supported",
    "load_supported",
    "predict_supported",
    "predict_proba_supported",
    "gpu_supported",
    "parallel_supported",
)


def _library_version(package: str | None) -> str | dict[str, str]:
    if not package:
        return {"status": "NOT_EXPOSED", "reason": "catalog package is not set"}
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return {"status": "DEPENDENCY_MISSING", "reason": f"{package} is not installed"}


def _not_exposed(name: str) -> dict[str, str]:
    return {
        "property": name,
        "status": "NOT_EXPOSED",
        "reason": "not exposed by this adapter/model",
    }


def _serializable_parameter_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serializable_parameter_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serializable_parameter_value(item) for key, item in value.items()}
    return repr(value)


def _effective_parameters(model: Any | None, params: dict[str, Any]) -> dict[str, Any]:
    result = {str(key): _serializable_parameter_value(value) for key, value in params.items()}
    if model is None:
        return result
    getter = getattr(model, "get_params", None)
    if callable(getter):
        try:
            exposed = getter(deep=False)
        except Exception:
            exposed = {}
        if isinstance(exposed, dict):
            result.update(
                {str(key): _serializable_parameter_value(value) for key, value in exposed.items()}
            )
    for key, value in vars(model).items():
        if key.startswith("_") or key in result:
            continue
        result[key] = _serializable_parameter_value(value)
    return result


def inspect_model_properties(
    spec: ModelSpec,
    model: Any | None,
    *,
    params: dict[str, Any] | None = None,
    artifact_path: str | Path | None = None,
    device: str | None = None,
    precision: str | None = None,
) -> dict[str, Any]:
    params = dict(params or {})
    result: dict[str, Any] = {name: _not_exposed(name) for name in PROPERTY_NAMES}
    result.update(
        {
            "model_id": spec.model_id,
            "class_name": spec.class_name,
            "library": spec.library,
            "library_version": _library_version(spec.package),
            "task": spec.task,
            "capabilities": list(spec.capabilities),
            "device": device or params.get("device", _not_exposed("device")),
            "precision": precision or params.get("precision", _not_exposed("precision")),
            "fit_supported": hasattr(model, "fit")
            if model is not None
            else spec.task in {"candidate", "position_series", "candidate_series"},
            "refit_supported": spec.task in {"candidate", "position_series", "candidate_series"},
            "incremental_supported": hasattr(model, "partial_fit") if model is not None else False,
            "save_supported": True,
            "load_supported": True,
            "predict_supported": hasattr(model, "predict") if model is not None else True,
            "predict_proba_supported": hasattr(model, "predict_proba")
            if model is not None
            else False,
            "gpu_supported": any(cap in spec.capabilities for cap in ("gpu", "gpu_optional")),
            "parallel_supported": any(cap in spec.capabilities for cap in ("auto_hpo", "ray"))
            or spec.library in {"sklearn", "lightgbm"},
            "effective_parameters": _effective_parameters(model, params),
        }
    )
    mapping = {
        "input_size": ("input_size",),
        "horizon": ("h", "horizon", "prediction_length"),
        "batch_size": ("batch_size",),
        "max_steps": ("max_steps",),
        "epochs": ("epochs", "max_epochs"),
        "learning_rate": ("learning_rate", "lr"),
        "random_seed": ("random_seed", "seed", "random_state"),
        "lags": ("lags",),
        "context_length": ("context_length",),
        "hidden_size": ("hidden_size", "d_model"),
        "layers": ("layers", "encoder_layers", "num_layers"),
        "heads": ("heads", "n_heads"),
        "dropout": ("dropout",),
        "n_series": ("n_series",),
        "backend": ("backend",),
        "num_samples": ("num_samples",),
        "loss": ("loss",),
        "optimizer": ("optimizer",),
        "dtype": ("dtype",),
    }
    for prop, names in mapping.items():
        for name in names:
            if name in params:
                result[prop] = params[name]
                break
            if model is not None and hasattr(model, name):
                result[prop] = getattr(model, name)
                break
    if artifact_path is not None:
        path = Path(artifact_path)
        result["model_file_path"] = str(path)

        summary = artifact_summary(path)

        if "size_bytes" in summary:
            result["model_file_size"] = summary["size_bytes"]

        if "sha256" in summary:
            result["model_sha256"] = summary["sha256"]

        result["artifact_type"] = summary.get(
            "artifact_type",
            "unknown",
        )
        result["artifact_file_count"] = summary.get(
            "file_count",
            0,
        )
    return result
