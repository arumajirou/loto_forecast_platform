from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any

import numpy as np
import pandas as pd

from .contracts import ArgumentState, ExpectedStatus, RuntimeStatus
from .data import validate_long_panel
from .inventory import MODEL_NAMES, model_contract


def discover_runtime_inventory(models_module: Any | None = None) -> dict[str, Any]:
    """Compare the pinned project inventory with an installed StatsForecast runtime."""

    if models_module is None:
        try:
            models_module = import_module("statsforecast.models")
        except ImportError as exc:
            return {
                "status": RuntimeStatus.DEPENDENCY_MISSING,
                "error": str(exc),
                "pinned_count": len(MODEL_NAMES),
                "runtime_exports": [],
                "missing": list(MODEL_NAMES),
                "missing_exports": list(MODEL_NAMES),
                "extra": [],
                "duplicate_exports": [],
                "export_order_matches": False,
                "complete": False,
            }
    exports = tuple(str(name) for name in getattr(models_module, "__all__", ()))
    available = {name for name in MODEL_NAMES if hasattr(models_module, name)}
    missing = sorted(set(MODEL_NAMES).difference(available))
    missing_exports = [name for name in MODEL_NAMES if name not in exports]
    extra = sorted(set(exports).difference(MODEL_NAMES))
    duplicate_exports = sorted({name for name in exports if exports.count(name) > 1})
    export_order_matches = exports == MODEL_NAMES
    complete = not missing and export_order_matches and not duplicate_exports
    return {
        "status": RuntimeStatus.VERIFIED if complete else RuntimeStatus.INVENTORY_MISMATCH,
        "pinned_count": len(MODEL_NAMES),
        "runtime_export_count": len(exports),
        "runtime_exports": list(exports),
        "available_count": len(available),
        "missing": missing,
        "missing_exports": missing_exports,
        "extra": extra,
        "duplicate_exports": duplicate_exports,
        "export_order_matches": export_order_matches,
        "complete": complete,
    }


def constructor_argument_ledger(
    model_class: type,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    signature = inspect.signature(model_class)
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    ledger: list[dict[str, Any]] = []
    rejected: list[str] = []
    for name, value in parameters.items():
        accepted = name in signature.parameters or accepts_kwargs
        state = ArgumentState.ACCEPTED if accepted else ArgumentState.REJECTED
        ledger.append({"argument": name, "state": state, "value_repr": repr(value)})
        if not accepted:
            rejected.append(name)
    if rejected:
        raise ValueError(f"constructor rejected arguments: {sorted(rejected)}")
    return ledger


def validate_forecast_output(
    prediction: pd.DataFrame,
    *,
    model_name: str,
    expected_rows: int,
    expected_unique_ids: set[str] | None = None,
    horizon: int | None = None,
) -> dict[str, Any]:
    contract = model_contract(model_name)
    ignored = {"unique_id", "ds", "cutoff"}
    value_columns = [column for column in prediction.columns if column not in ignored]
    identity_ok = {"unique_id", "ds"}.issubset(prediction.columns)
    shape_ok = len(prediction) == expected_rows and bool(value_columns)
    duplicate_keys = bool(identity_ok and prediction.duplicated(["unique_id", "ds"]).any())
    finite = bool(
        value_columns
        and np.isfinite(prediction[value_columns].to_numpy(dtype=float)).all()
    )

    series_horizon_ok = True
    if expected_unique_ids is not None or horizon is not None:
        if not identity_ok or expected_unique_ids is None or horizon is None:
            series_horizon_ok = False
        else:
            observed_ids = {str(value) for value in prediction["unique_id"].unique()}
            expected_ids = {str(value) for value in expected_unique_ids}
            counts = prediction.groupby("unique_id", sort=False).size()
            series_horizon_ok = observed_ids == expected_ids and bool((counts == horizon).all())

    if contract.expected_status is ExpectedStatus.EXPECTED_NEGATIVE_PASS:
        passed = (
            identity_ok
            and shape_ok
            and not finite
            and not duplicate_keys
            and series_horizon_ok
        )
        return {
            "status": (
                RuntimeStatus.EXPECTED_NEGATIVE_PASS
                if passed
                else RuntimeStatus.VALIDATION_FAILED
            ),
            "finite": finite,
            "shape_ok": shape_ok,
            "identity_ok": identity_ok,
            "series_horizon_ok": series_horizon_ok,
            "duplicate_keys": duplicate_keys,
            "champion_eligible": False,
        }
    passed = identity_ok and shape_ok and finite and not duplicate_keys and series_horizon_ok
    return {
        "status": RuntimeStatus.VERIFIED if passed else RuntimeStatus.VALIDATION_FAILED,
        "finite": finite,
        "shape_ok": shape_ok,
        "identity_ok": identity_ok,
        "series_horizon_ok": series_horizon_ok,
        "duplicate_keys": duplicate_keys,
        "champion_eligible": contract.champion_eligible,
    }


def _validate_model_data_preconditions(
    panel: pd.DataFrame,
    *,
    model_name: str,
    parameters: dict[str, Any],
) -> None:
    contract = model_contract(model_name)
    if contract.minimum_seasons is None:
        return
    season_length = parameters.get("season_length")
    if isinstance(season_length, int) and not isinstance(season_length, bool):
        seasonalities = (season_length,)
    elif isinstance(season_length, (list, tuple)) and season_length:
        seasonalities = tuple(season_length)
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
            for value in seasonalities
        ):
            raise ValueError("season_length values must be positive integers")
    else:
        raise ValueError(
            f"model {model_name} requires integer or non-empty sequence season_length"
        )
    if any(value < 1 for value in seasonalities):
        raise ValueError("season_length values must be positive")
    required_rows = contract.minimum_seasons * max(seasonalities)
    too_short = {
        str(unique_id): len(group)
        for unique_id, group in panel.groupby("unique_id", sort=False)
        if len(group) < required_rows
    }
    if too_short:
        raise ValueError(
            f"model {model_name} requires at least {required_rows} rows per series: {too_short}"
        )


def _runtime_device_evidence() -> dict[str, Any]:
    return {
        "device": "cpu",
        "device_type": "cpu",
        "gpu_not_applicable": True,
        "gpu_pid": None,
        "vram_mb": None,
        "cpu_fallback": False,
        "n_jobs": 1,
    }


class StatsForecastRuntimeAdapter:
    """Small injected-runtime adapter kept independent from shared orchestration."""

    def __init__(self, *, core_class: type, models_module: Any) -> None:
        self.core_class = core_class
        self.models_module = models_module

    def build_model(self, name: str, parameters: dict[str, Any] | None = None) -> Any:
        contract = model_contract(name)
        parameters = dict(parameters or {})
        missing = [item for item in contract.required_parameters if item not in parameters]
        if missing:
            raise ValueError(f"model {name} requires parameters: {missing}")
        if contract.requires_explicit_configuration and not parameters:
            raise ValueError(f"model {name} requires explicit constructor configuration")
        try:
            model_class = getattr(self.models_module, name)
        except AttributeError as exc:
            raise LookupError(f"installed runtime does not expose {name}") from exc
        constructor_argument_ledger(model_class, parameters)
        return model_class(**parameters)

    def forecast(
        self,
        panel: pd.DataFrame,
        *,
        model_name: str,
        freq: int | str,
        horizon: int,
        parameters: dict[str, Any] | None = None,
        levels: tuple[int, ...] | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        validate_long_panel(panel)
        if horizon < 1:
            raise ValueError("horizon must be positive")
        if levels is not None:
            if not levels or len(levels) != len(set(levels)):
                raise ValueError("levels must be non-empty and unique when provided")
            if any(level <= 0 or level >= 100 for level in levels):
                raise ValueError("levels must be between 0 and 100")
        resolved_parameters = dict(parameters or {})
        _validate_model_data_preconditions(
            panel,
            model_name=model_name,
            parameters=resolved_parameters,
        )
        model = self.build_model(model_name, resolved_parameters)
        engine = self.core_class(models=[model], freq=freq, n_jobs=1)
        level_values = None if levels is None else list(levels)
        prediction = engine.forecast(
            df=panel.copy(deep=True),
            h=horizon,
            level=level_values,
        )
        unique_ids = {str(value) for value in panel["unique_id"].unique()}
        expected_rows = len(unique_ids) * horizon
        evidence = validate_forecast_output(
            prediction,
            model_name=model_name,
            expected_rows=expected_rows,
            expected_unique_ids=unique_ids,
            horizon=horizon,
        )
        evidence.update(_runtime_device_evidence())
        evidence.update(
            {
                "forecast_mode": "point" if levels is None else "interval",
                "requested_levels": [] if levels is None else list(levels),
            }
        )
        return prediction, evidence
