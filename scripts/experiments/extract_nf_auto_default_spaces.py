from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast.auto as auto_module
from neuralforecast.common._base_auto import (
    BaseAuto,
    MockTrial,
)

CLASSIFICATION = Path(
    "artifacts/parameter_inventory/neuralforecast_auto_model_classification_v2.json"
)

OUTPUT = Path("artifacts/parameter_inventory/neuralforecast_auto_default_spaces.json")


def encode(value: Any) -> Any:
    if isinstance(
        value,
        (str, int, float, bool, type(None)),
    ):
        return value

    if isinstance(value, tuple):
        return [encode(item) for item in value]

    if isinstance(value, list):
        return [encode(item) for item in value]

    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}

    return repr(value)


classification = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))

eligible = {
    record["auto_model"]
    for record in classification["records"]
    if record["eligible_current_policy"]
}

records = []

for name in sorted(eligible):
    cls = getattr(auto_module, name)

    if not (inspect.isclass(cls) and issubclass(cls, BaseAuto)):
        continue

    entry: dict[str, Any] = {
        "auto_model": name,
        "backends": {},
    }

    for backend in ("optuna", "ray"):
        try:
            try:
                config_fn = cls.get_default_config(
                    h=1,
                    backend=backend,
                    n_series=7,
                )
            except TypeError:
                config_fn = cls.get_default_config(
                    h=1,
                    backend=backend,
                )

            if callable(config_fn):
                try:
                    resolved = config_fn(MockTrial())
                except Exception as exc:
                    entry["backends"][backend] = {
                        "status": "CONFIG_EVALUATION_ERROR",
                        "error": repr(exc),
                        "callable_repr": repr(config_fn),
                    }
                    continue
            else:
                resolved = config_fn

            entry["backends"][backend] = {
                "status": "OK",
                "resolved_config": encode(resolved),
                "parameter_count": (len(resolved) if isinstance(resolved, dict) else None),
            }

        except Exception as exc:
            entry["backends"][backend] = {
                "status": "GET_DEFAULT_ERROR",
                "error": repr(exc),
            }

    records.append(entry)

OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT.write_text(
    json.dumps(
        records,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

for record in records:
    print(f"\n=== {record['auto_model']} ===")

    for backend, result in record["backends"].items():
        print(
            backend,
            result["status"],
            "parameters=",
            result.get("parameter_count"),
        )

        if result["status"] != "OK":
            print("  ", result.get("error"))

print("\nmodels=", len(records))
print("OUT=", OUTPUT)
print("AUTO_DEFAULT_SPACES_EXTRACTION=PASS")
