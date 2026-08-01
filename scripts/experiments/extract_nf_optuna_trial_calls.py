from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast.auto as auto_module
from neuralforecast.common._base_auto import BaseAuto


CLASSIFICATION = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_auto_model_classification_v2.json"
)

OUTPUT = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_optuna_trial_calls.json"
)


class RecordingTrial:
    """Optuna Trial-compatible recorder.

    Supports both current suggest_float/suggest_int APIs and
    legacy suggest_uniform/suggest_loguniform APIs still used by
    some NeuralForecast 3.2.0 default search-space definitions.
    """

    def __init__(
        self,
        categorical_strategy: str = "first",
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.categorical_strategy = categorical_strategy

        # Compatibility attributes occasionally referenced by
        # Optuna-compatible configuration functions.
        self.number = 0
        self.params: dict[str, Any] = {}
        self.user_attrs: dict[str, Any] = {}
        self.system_attrs: dict[str, Any] = {}

    def _record(
        self,
        record: dict[str, Any],
        value: Any,
    ) -> Any:
        self.calls.append(record)
        self.params[record["parameter"]] = value
        return value

    def _choose(
        self,
        values: list[Any],
    ) -> Any:
        if not values:
            raise ValueError(
                "suggest_categorical received no choices"
            )

        strategy = self.categorical_strategy

        if strategy == "last":
            return values[-1]

        if strategy == "middle":
            return values[len(values) // 2]

        return values[0]

    def suggest_categorical(
        self,
        name: str,
        choices: list[Any] | tuple[Any, ...],
    ) -> Any:
        values = list(choices)
        selected = self._choose(values)

        return self._record(
            {
                "parameter": name,
                "kind": "categorical",
                "choices": values,
            },
            selected,
        )

    def suggest_float(
        self,
        name: str,
        low: float,
        high: float,
        *,
        step: float | None = None,
        log: bool = False,
    ) -> float:
        if log and step is not None:
            raise ValueError(
                "Optuna does not allow log=True with step"
            )

        kind = (
            "log_float"
            if log
            else (
                "discrete_float"
                if step is not None
                else "float"
            )
        )

        selected = float(low)

        return self._record(
            {
                "parameter": name,
                "kind": kind,
                "low": float(low),
                "high": float(high),
                "step": (
                    None
                    if step is None
                    else float(step)
                ),
                "log": bool(log),
                "api": "suggest_float",
            },
            selected,
        )

    def suggest_int(
        self,
        name: str,
        low: int,
        high: int,
        *,
        step: int = 1,
        log: bool = False,
    ) -> int:
        selected = int(low)

        return self._record(
            {
                "parameter": name,
                "kind": (
                    "log_int"
                    if log
                    else "integer"
                ),
                "low": int(low),
                "high": int(high),
                "step": int(step),
                "log": bool(log),
                "api": "suggest_int",
            },
            selected,
        )

    # -------------------------------------------------
    # Legacy Optuna compatibility methods
    # -------------------------------------------------

    def suggest_uniform(
        self,
        name: str,
        low: float,
        high: float,
    ) -> float:
        selected = float(low)

        return self._record(
            {
                "parameter": name,
                "kind": "float",
                "low": float(low),
                "high": float(high),
                "step": None,
                "log": False,
                "api": "suggest_uniform",
            },
            selected,
        )

    def suggest_loguniform(
        self,
        name: str,
        low: float,
        high: float,
    ) -> float:
        selected = float(low)

        return self._record(
            {
                "parameter": name,
                "kind": "log_float",
                "low": float(low),
                "high": float(high),
                "step": None,
                "log": True,
                "api": "suggest_loguniform",
            },
            selected,
        )

    def suggest_discrete_uniform(
        self,
        name: str,
        low: float,
        high: float,
        q: float,
    ) -> float:
        selected = float(low)

        return self._record(
            {
                "parameter": name,
                "kind": "discrete_float",
                "low": float(low),
                "high": float(high),
                "step": float(q),
                "log": False,
                "api": "suggest_discrete_uniform",
            },
            selected,
        )

    # -------------------------------------------------
    # Optional Trial compatibility helpers
    # -------------------------------------------------

    def set_user_attr(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.user_attrs[key] = value

    def set_system_attr(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.system_attrs[key] = value

    def report(
        self,
        value: float,
        step: int,
    ) -> None:
        return None

    def should_prune(self) -> bool:
        return False


classification = json.loads(
    CLASSIFICATION.read_text(encoding="utf-8")
)

eligible = [
    record["auto_model"]
    for record in classification["records"]
    if record["eligible_current_policy"]
]

records = []

for name in sorted(eligible):
    cls = getattr(auto_module, name)

    if not (
        inspect.isclass(cls)
        and issubclass(cls, BaseAuto)
    ):
        continue

    trial = RecordingTrial(
        categorical_strategy="first",
    )

    try:
        try:
            config_fn = cls.get_default_config(
                h=1,
                backend="optuna",
                n_series=7,
            )
        except TypeError:
            config_fn = cls.get_default_config(
                h=1,
                backend="optuna",
            )

        resolved = (
            config_fn(trial)
            if callable(config_fn)
            else config_fn
        )

        records.append(
            {
                "auto_model": name,
                "status": "OK",
                "trial_calls": trial.calls,
                "resolved_config": resolved,
                "params": trial.params,
            }
        )

    except Exception as exc:
        records.append(
            {
                "auto_model": name,
                "status": "ERROR",
                "error": repr(exc),
                "trial_calls": trial.calls,
                "params": trial.params,
            }
        )

OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT.write_text(
    json.dumps(
        records,
        indent=2,
        ensure_ascii=False,
        default=repr,
    ),
    encoding="utf-8",
)

errors = [
    record
    for record in records
    if record["status"] != "OK"
]

for record in records:
    print(
        f"{record['auto_model']:28s}",
        record["status"],
        "trial_calls=",
        len(record.get("trial_calls", [])),
    )

    if record["status"] != "OK":
        print(
            "  error=",
            record.get("error"),
        )

print("models=", len(records))
print("errors=", len(errors))
print("OUT=", OUTPUT)

if errors:
    print("OPTUNA_TRIAL_CALL_EXTRACTION=PARTIAL")
else:
    print("OPTUNA_TRIAL_CALL_EXTRACTION=PASS")
