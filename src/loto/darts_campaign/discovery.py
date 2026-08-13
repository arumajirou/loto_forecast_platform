from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable
from typing import Any

from loto.models.darts_source_inventory import PUBLIC_FORECASTING_EXPORTS_0_46_1

_SIGNATURE_METHODS = (
    "fit",
    "predict",
    "historical_forecasts",
    "backtest",
    "residuals",
    "save",
    "load",
)
_SUPPORT_NAMES = (
    "supports_past_covariates",
    "supports_future_covariates",
    "supports_static_covariates",
    "supports_multivariate",
    "supports_probabilistic_prediction",
    "supports_sample_weight",
    "supports_likelihood_parameter_prediction",
)


def _signature(value: Any) -> str | None:
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return None


def _failure_status(exc: Exception) -> str:
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return "DEPENDENCY_MISSING"
    return "IMPORT_FAILED"


def discover_models(
    models_module: Any | None = None,
    names: Iterable[str] = PUBLIC_FORECASTING_EXPORTS_0_46_1,
) -> list[dict[str, Any]]:
    """Discover public forecasting exports and retain every failure as a row."""

    module = models_module or importlib.import_module("darts.models")
    rows: list[dict[str, Any]] = []
    for public_name in names:
        try:
            value = getattr(module, public_name)
        except Exception as exc:
            rows.append(
                {
                    "public_name": public_name,
                    "status": _failure_status(exc),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            continue

        is_class = inspect.isclass(value)
        is_abstract = bool(is_class and inspect.isabstract(value))
        canonical_name = getattr(value, "__name__", type(value).__name__)
        row: dict[str, Any] = {
            "public_name": public_name,
            "status": "ABSTRACT" if is_abstract else ("IMPORTED" if is_class else "NOT_CLASS"),
            "module": getattr(value, "__module__", None),
            "class_name": canonical_name,
            "is_class": is_class,
            "is_abstract": is_abstract,
            "is_alias": canonical_name != public_name,
            "constructor_signature": _signature(value) if is_class else None,
        }
        for method_name in _SIGNATURE_METHODS:
            method = getattr(value, method_name, None)
            row[f"{method_name}_signature"] = _signature(method) if method is not None else None
        for support_name in _SUPPORT_NAMES:
            declared = inspect.getattr_static(value, support_name, None) is not None
            row[f"declares_{support_name}"] = declared
        rows.append(row)
    return rows
