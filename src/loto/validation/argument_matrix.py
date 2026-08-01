from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from loto.models.catalog import ModelSpec

# Parameters that are orchestration/runtime concerns rather than constructor arguments.
RUNTIME_ARGUMENTS: tuple[str, ...] = (
    "device",
    "precision",
    "seed",
    "timeout",
    "cpus",
    "gpus",
    "parallel_trials",
)

# Conservative smoke values. These values minimise work and avoid changing semantic
# switches whose valid domain cannot be inferred safely from a Python signature.
SMOKE_VALUES: dict[str, Any] = {
    "h": 1,
    "horizon": 1,
    "prediction_length": 1,
    "input_size": 8,
    "context_length": 8,
    "max_steps": 1,
    "max_epochs": 1,
    "epochs": 1,
    "num_samples": 1,
    "n_samples": 1,
    "batch_size": 8,
    "windows_batch_size": 16,
    "inference_windows_batch_size": 16,
    "num_batches_per_epoch": 1,
    "n_estimators": 2,
    "iterations": 2,
    "max_iter": 2,
    "n_jobs": 1,
    "num_leaves": 4,
    "max_depth": 2,
    "hidden_size": 8,
    "encoder_hidden_size": 8,
    "decoder_hidden_size": 8,
    "n_layers": 1,
    "num_layers": 1,
    "encoder_layers": 1,
    "decoder_layers": 1,
    "n_heads": 1,
    "heads": 1,
    "dropout": 0.0,
    "learning_rate": 0.001,
    "lr": 0.001,
    "random_seed": 42,
    "random_state": 42,
    "seed": 42,
    "verbose": False,
    "enable_progress_bar": False,
    "enable_checkpointing": False,
    "refit_with_val": False,
    "parallel_trials": 1,
    "cpus": 1,
    "gpus": 0,
}

MODULE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "sklearn": (
        "sklearn.linear_model",
        "sklearn.ensemble",
        "sklearn.ensemble._hist_gradient_boosting.gradient_boosting",
    ),
    "lightgbm": ("lightgbm",),
    "xgboost": ("xgboost",),
    "catboost": ("catboost",),
    "statsforecast": ("statsforecast.models",),
    "neuralforecast": ("neuralforecast.models",),
    "neuralforecast_auto": ("neuralforecast.auto",),
    "hierarchicalforecast": ("hierarchicalforecast.methods",),
    "mlforecast_auto": ("mlforecast.auto",),
}


@dataclass(frozen=True)
class ArgumentInventory:
    model_id: str
    library: str
    class_name: str
    argument: str
    kind: str
    required: bool
    default: Any
    source: str
    smoke_value: Any
    smoke_eligible: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArgumentCase:
    case_id: str
    model_id: str
    profile: str
    changed_argument: str | None
    requested_params: dict[str, Any]
    expected_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_class(spec: ModelSpec) -> type[Any] | None:
    for module_name in MODULE_CANDIDATES.get(spec.library, ()):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        candidate = getattr(module, spec.class_name, None)
        if inspect.isclass(candidate):
            return candidate
    return None


def _signature_rows(spec: ModelSpec) -> list[ArgumentInventory]:
    cls = _resolve_class(spec)
    if cls is None:
        return []
    try:
        signature = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return []

    rows: list[ArgumentInventory] = []
    for name, parameter in signature.parameters.items():
        if name == "self" or parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        required = parameter.default is inspect.Parameter.empty
        default = None if required else parameter.default
        smoke_eligible = name in SMOKE_VALUES
        rows.append(
            ArgumentInventory(
                model_id=spec.model_id,
                library=spec.library,
                class_name=spec.class_name,
                argument=name,
                kind=parameter.kind.name,
                required=required,
                default=default,
                source="constructor_signature",
                smoke_value=SMOKE_VALUES.get(name),
                smoke_eligible=smoke_eligible,
                reason=(
                    "known bounded smoke value"
                    if smoke_eligible
                    else "not mutated automatically; domain or interaction is model-specific"
                ),
            )
        )
    return rows


def build_argument_inventory(specs: Iterable[ModelSpec]) -> list[ArgumentInventory]:
    """Return one auditable row for every discoverable model argument.

    Constructor signatures are preferred. Catalog defaults and runtime arguments are
    then added so adapter-level settings are not silently omitted.
    """

    rows: list[ArgumentInventory] = []
    seen: set[tuple[str, str]] = set()
    for spec in specs:
        for row in _signature_rows(spec):
            rows.append(row)
            seen.add((spec.model_id, row.argument))
        for name, default in spec.default_params.items():
            key = (spec.model_id, name)
            if key in seen:
                continue
            rows.append(
                ArgumentInventory(
                    model_id=spec.model_id,
                    library=spec.library,
                    class_name=spec.class_name,
                    argument=name,
                    kind="CATALOG",
                    required=False,
                    default=default,
                    source="catalog_default_params",
                    smoke_value=SMOKE_VALUES.get(name, default),
                    smoke_eligible=name in SMOKE_VALUES,
                    reason=(
                        "catalog argument with bounded smoke value"
                        if name in SMOKE_VALUES
                        else "catalog argument retained at declared default"
                    ),
                )
            )
            seen.add(key)
        for name in RUNTIME_ARGUMENTS:
            key = (spec.model_id, name)
            if key in seen:
                continue
            rows.append(
                ArgumentInventory(
                    model_id=spec.model_id,
                    library=spec.library,
                    class_name=spec.class_name,
                    argument=name,
                    kind="RUNTIME",
                    required=False,
                    default=None,
                    source="orchestration_runtime",
                    smoke_value=SMOKE_VALUES.get(name),
                    smoke_eligible=name in SMOKE_VALUES,
                    reason="validated by runtime/property evidence rather than constructor",
                )
            )
            seen.add(key)
    return rows


def build_smoke_cases(
    specs: Iterable[ModelSpec],
    inventory: Iterable[ArgumentInventory],
    *,
    profile: str = "quick",
) -> list[ArgumentCase]:
    """Build bounded lifecycle cases.

    ``quick`` creates one maximal-safe case per model. ``oat`` additionally creates
    one-at-a-time cases for every argument with a known safe smoke value. This is
    exhaustive over discoverable arguments without attempting an infeasible Cartesian
    product of all values.
    """

    if profile not in {"quick", "oat"}:
        raise ValueError("profile must be 'quick' or 'oat'")
    by_model: dict[str, list[ArgumentInventory]] = {}
    for row in inventory:
        by_model.setdefault(row.model_id, []).append(row)

    cases: list[ArgumentCase] = []
    checks = (
        "fit",
        "predict",
        "save",
        "load",
        "reload_predict",
        "property_reflection",
        "argument_verification",
        "retrain",
        "retrain_predict",
        "artifact_hash",
    )
    for spec in specs:
        base = dict(spec.default_params)
        for row in by_model.get(spec.model_id, []):
            if row.smoke_eligible and row.argument in {
                "max_steps",
                "max_epochs",
                "epochs",
                "num_samples",
                "batch_size",
                "windows_batch_size",
                "n_estimators",
                "iterations",
                "max_iter",
                "n_jobs",
                "parallel_trials",
                "cpus",
                "gpus",
            }:
                base[row.argument] = row.smoke_value
        cases.append(
            ArgumentCase(
                case_id=f"{spec.model_id}__quick",
                model_id=spec.model_id,
                profile="quick",
                changed_argument=None,
                requested_params=base,
                expected_checks=checks,
            )
        )
        if profile == "oat":
            for row in by_model.get(spec.model_id, []):
                if not row.smoke_eligible:
                    continue
                params = dict(base)
                params[row.argument] = row.smoke_value
                cases.append(
                    ArgumentCase(
                        case_id=f"{spec.model_id}__arg__{row.argument}",
                        model_id=spec.model_id,
                        profile="oat",
                        changed_argument=row.argument,
                        requested_params=params,
                        expected_checks=checks,
                    )
                )
    return cases
