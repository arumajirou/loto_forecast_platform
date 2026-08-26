"""Build the fail-visible 250-identity inventory for the Bingo5 pilot."""

from __future__ import annotations

import importlib
import inspect
from copy import deepcopy
from importlib import metadata
from typing import Any

from loto.evaluation.probabilistic_oof_adapter import build_probabilistic_scientific_plan
from loto.models.catalog_full import ModelEntry, build_catalog
from loto.statsforecast.certification_models import (
    _DEFAULTS as STATSFORECAST_CERTIFICATION_DEFAULTS,
)

from .contracts import ModelInventoryRow, ParameterCategory, ParameterDescriptor

_TARGET_GAME = "bingo5"
_EXPECTED_IDENTITIES = 250

_RUNTIME_NAMES = {
    "batch_size",
    "callbacks",
    "cpus",
    "device",
    "devices",
    "gpus",
    "logger",
    "n_jobs",
    "num_threads",
    "num_workers",
    "parallel_trials",
    "precision",
    "random_state",
    "seed",
    "verbose",
}
_OUTPUT_CONTROL_NAMES = {
    "alias",
    "callbacks",
    "logger",
    "prediction_intervals",
    "verbose",
}
_DATA_DEPENDENT_NAMES = {
    "context_length",
    "h",
    "horizon",
    "input_size",
    "lags",
    "season_length",
    "test_size",
    "window_size",
}
_UNSAFE_NAMES = {
    "callback",
    "callbacks",
    "logger",
    "model",
    "prediction_intervals",
}
_TUNABLE_NAMES = {
    "alpha",
    "alpha_d",
    "alpha_p",
    "beta",
    "dropout",
    "hidden_size",
    "input_size",
    "l1_ratio",
    "lags",
    "learning_rate",
    "max_depth",
    "n_estimators",
    "num_layers",
    "num_leaves",
    "season_length",
    "test_size",
    "window_size",
}


def _safe_version(package: str | None) -> str | None:
    if not package:
        return None
    candidates = {
        "sklearn": "scikit-learn",
        "chronos": "chronos-forecasting",
    }
    try:
        return metadata.version(candidates.get(package, package))
    except metadata.PackageNotFoundError:
        return None


def _candidate_modules(entry: ModelEntry) -> tuple[str, ...]:
    mapping: dict[str, tuple[str, ...]] = {
        "statsforecast": ("statsforecast.models",),
        "neuralforecast": ("neuralforecast.models",),
        "neuralforecast_auto": ("neuralforecast.auto",),
        "mlforecast_auto": ("mlforecast.auto",),
        "sklearn": (
            "sklearn.linear_model",
            "sklearn.ensemble",
            "sklearn.experimental",
        ),
        "lightgbm": ("lightgbm",),
        "xgboost": ("xgboost",),
        "catboost": ("catboost",),
        "reservoirpy": ("reservoirpy",),
        "darts": ("darts.models",),
        "gluonts": ("gluonts.model.deepar",),
        "skforecast": ("skforecast.recursive",),
        "sktime": ("sktime.forecasting.compose",),
    }
    return mapping.get(entry.library, ())


def _resolve_constructor(entry: ModelEntry) -> type[Any] | None:
    for module_name in _candidate_modules(entry):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        candidate = getattr(module, entry.class_name, None)
        if inspect.isclass(candidate):
            return candidate
    return None


def _annotation_repr(value: Any) -> str | None:
    if value is inspect.Parameter.empty:
        return None
    return str(value)


def _classify_parameter(name: str, *, required: bool) -> tuple[ParameterCategory, bool, str]:
    if name in _UNSAFE_NAMES:
        return (
            ParameterCategory.UNSUPPORTED_OR_UNSAFE,
            False,
            "control/wrapper object is not safe for automatic accuracy search",
        )
    if name in _RUNTIME_NAMES:
        return (
            ParameterCategory.RUNTIME_RESOURCE,
            False,
            "runtime/resource controls are recorded but not accuracy-tuned",
        )
    if name in _DATA_DEPENDENT_NAMES:
        return (
            ParameterCategory.DATA_DEPENDENT,
            name in _TUNABLE_NAMES,
            "data-dependent parameter requires train-length/model constraints",
        )
    if name in _OUTPUT_CONTROL_NAMES:
        return (
            ParameterCategory.OUTPUT_CONTROL,
            False,
            "output/control argument is excluded from accuracy search",
        )
    if name in _TUNABLE_NAMES:
        return (
            ParameterCategory.TUNABLE_HYPERPARAMETER,
            True,
            "known accuracy-affecting hyperparameter; bounded space still requires provenance",
        )
    if required:
        return (
            ParameterCategory.IDENTITY_CONFIGURATION,
            False,
            "required constructor argument with no approved generic search rule",
        )
    return (
        ParameterCategory.IDENTITY_CONFIGURATION,
        False,
        "constructor option retained in inventory but not automatically tuned",
    )


def _inspect_parameters(
    constructor: type[Any] | None,
) -> tuple[
    str | None,
    tuple[str, ...],
    tuple[str, ...],
    dict[str, str],
    tuple[ParameterDescriptor, ...],
]:
    if constructor is None:
        return None, (), (), {}, ()
    try:
        signature = inspect.signature(constructor)
    except (TypeError, ValueError):
        return None, (), (), {}, ()

    required: list[str] = []
    optional: list[str] = []
    upstream_defaults: dict[str, str] = {}
    descriptors: list[ParameterDescriptor] = []
    for name, parameter in signature.parameters.items():
        if name == "self" or parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        is_required = parameter.default is inspect.Parameter.empty
        if is_required:
            required.append(name)
            default_repr = None
        else:
            optional.append(name)
            default_repr = repr(parameter.default)
            upstream_defaults[name] = default_repr
        category, tunable, reason = _classify_parameter(name, required=is_required)
        descriptors.append(
            ParameterDescriptor(
                name=name,
                annotation=_annotation_repr(parameter.annotation),
                required=is_required,
                default_repr=default_repr,
                category=category,
                tunable=tunable,
                provenance=("inspect.signature(installed runtime)",),
                reason=reason,
            )
        )
    return (
        str(signature),
        tuple(required),
        tuple(optional),
        upstream_defaults,
        tuple(descriptors),
    )


def _adapter_name(entry: ModelEntry) -> str:
    if entry.task == "candidate":
        return "RuntimeModel(slot-conditioned-candidate)"
    if entry.task == "reconciliation":
        return "none"
    return "PositionSeriesWorker"


def _known_support(entry: ModelEntry) -> tuple[bool | None, str | None]:
    if entry.task == "reconciliation":
        return False, "NON_STANDALONE_METHOD"
    if entry.class_name == "AutoHINT":
        return False, "UNSUPPORTED_GAME: AutoHINT requires exactly seven coherent series"
    if entry.class_name == "NaNModel":
        return False, "EXPECTED_NEGATIVE_CONTROL"
    if entry.class_name == "SklearnModel":
        return False, "NOT_ROUTABLE: wrapper/exogenous lane requires explicit wrapped estimator"
    return None, "NOT_YET_SMOKED"


def build_bingo5_inventory() -> list[ModelInventoryRow]:
    """Return exactly one row per canonical scientific identity for Bingo5."""

    broad = build_catalog()
    routes = build_probabilistic_scientific_plan((_TARGET_GAME,))
    broad_ids = {entry.model_id for entry in broad}
    route_ids = {route.model_id for route in routes}
    collisions = sorted(broad_ids & route_ids)
    if collisions:
        raise AssertionError(
            f"identity collision between broad/probabilistic catalogs: {collisions}"
        )
    observed = len(broad) + len(routes)
    if observed != _EXPECTED_IDENTITIES:
        raise RuntimeError(
            f"Bingo5 identity universe mismatch: expected={_EXPECTED_IDENTITIES} observed={observed}"
        )

    sf_defaults = deepcopy(STATSFORECAST_CERTIFICATION_DEFAULTS)
    rows: list[ModelInventoryRow] = []
    for entry in broad:
        constructor = _resolve_constructor(entry)
        signature, required, optional, upstream_defaults, descriptors = _inspect_parameters(
            constructor
        )
        supports_bingo5, reason = _known_support(entry)
        capabilities = set(entry.capabilities)
        rows.append(
            ModelInventoryRow(
                model_id=entry.model_id,
                source="catalog",
                library=entry.library,
                class_name=entry.class_name,
                family=entry.family,
                task=entry.task,
                provider=entry.library,
                adapter=_adapter_name(entry),
                runtime=entry.package or entry.library,
                package=entry.package,
                installed_version=_safe_version(entry.package),
                constructor_signature=signature,
                required_args=required,
                optional_args=optional,
                current_default_params=deepcopy(entry.default_params),
                certification_params=deepcopy(sf_defaults.get(entry.class_name, {}))
                if entry.library == "statsforecast"
                else {},
                upstream_defaults=upstream_defaults,
                supports_univariate=not entry.requires_n_series,
                supports_exog=entry.supports_exogenous,
                supports_probabilistic=entry.supports_probabilistic,
                supports_gpu=True
                if ("gpu" in capabilities or "gpu_optional" in capabilities)
                else None,
                supports_cpu=None,
                supports_bingo5=supports_bingo5,
                reason_if_not_supported=reason,
                parameter_inventory=descriptors,
            )
        )

    for route in routes:
        rows.append(
            ModelInventoryRow(
                model_id=route.model_id,
                source="probabilistic",
                library="probabilistic",
                class_name=None,
                family=route.family,
                task=route.target_mode or "probabilistic",
                provider=route.backend,
                adapter="probabilistic_oof_adapter",
                runtime=route.backend,
                package=None,
                installed_version=None,
                supports_univariate=True,
                supports_exog=False,
                supports_probabilistic=True,
                supports_gpu=None,
                supports_cpu=None,
                supports_bingo5=bool(route.allowed),
                reason_if_not_supported=None
                if route.allowed
                else f"{route.reason_code}: {route.details}",
            )
        )

    rows.sort(key=lambda row: (row.source, row.library, row.model_id))
    if len({row.model_id for row in rows}) != _EXPECTED_IDENTITIES:
        raise AssertionError("Bingo5 inventory contains duplicate or missing model identities")
    return rows
