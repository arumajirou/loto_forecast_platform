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
                "extra": [],
            }
    exports = tuple(str(name) for name in getattr(models_module, "__all__", ()))
    available = {name for name in MODEL_NAMES if hasattr(models_module, name)}
    return {
        "status": RuntimeStatus.VERIFIED if available else RuntimeStatus.VALIDATION_FAILED,
        "pinned_count": len(MODEL_NAMES),
        "runtime_export_count": len(exports),
        "runtime_exports": list(exports),
        "missing": sorted(set(MODEL_NAMES).difference(available)),
        "extra": sorted(set(exports).difference(MODEL_NAMES)),
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
) -> dict[str, Any]:
    contract = model_contract(model_name)
    value_columns = [column for column in prediction.columns if column not in {"unique_id", "ds"}]
    identity_ok = {"unique_id", "ds"}.issubset(prediction.columns)
    shape_ok = len(prediction) == expected_rows and bool(value_columns)
    duplicate_keys = bool(
        identity_ok and prediction.duplicated(["unique_id", "ds"]).any()
    )
    finite = bool(
        value_columns
        and np.isfinite(prediction[value_columns].to_numpy(dtype=float)).all()
    )
    if contract.expected_status is ExpectedStatus.EXPECTED_NEGATIVE_PASS:
        passed = identity_ok and shape_ok and not finite
        return {
            "status": (
                RuntimeStatus.EXPECTED_NEGATIVE_PASS
                if passed
                else RuntimeStatus.VALIDATION_FAILED
            ),
            "finite": finite,
            "shape_ok": shape_ok,
            "identity_ok": identity_ok,
            "duplicate_keys": duplicate_keys,
            "champion_eligible": False,
        }
    passed = identity_ok and shape_ok and finite and not duplicate_keys
    return {
        "status": RuntimeStatus.VERIFIED if passed else RuntimeStatus.VALIDATION_FAILED,
        "finite": finite,
        "shape_ok": shape_ok,
        "identity_ok": identity_ok,
        "duplicate_keys": duplicate_keys,
        "champion_eligible": contract.champion_eligible,
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
        if missing and "minimum_two_seasons" not in missing:
            raise ValueError(f"model {name} requires parameters: {missing}")
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
        levels: tuple[int, ...] = (80, 90),
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        validate_long_panel(panel)
        model = self.build_model(model_name, parameters)
        engine = self.core_class(models=[model], freq=freq, n_jobs=1)
        prediction = engine.forecast(df=panel.copy(deep=True), h=horizon, level=list(levels))
        expected_rows = panel["unique_id"].nunique() * horizon
        evidence = validate_forecast_output(
            prediction,
            model_name=model_name,
            expected_rows=expected_rows,
        )
        return prediction, evidence
