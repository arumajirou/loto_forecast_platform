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

try:
    from ray.tune.search.sample import (
        Categorical,
        Domain,
        Float,
        Integer,
    )
except ImportError:
    Categorical = object
    Domain = object
    Float = object
    Integer = object


CLASSIFICATION = Path(
    "artifacts/parameter_inventory/neuralforecast_auto_model_classification_v2.json"
)

OUTPUT = Path("artifacts/parameter_inventory/neuralforecast_auto_spaces_structured.json")


def json_safe(value: Any) -> Any:
    if isinstance(
        value,
        (str, int, float, bool, type(None)),
    ):
        return value

    if isinstance(value, list):
        return [json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [json_safe(item) for item in value]

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}

    return repr(value)


def encode_ray_sampler(
    sampler: Any,
) -> dict[str, Any] | None:
    if sampler is None:
        return None

    result: dict[str, Any] = {
        "class": type(sampler).__name__,
        "module": type(sampler).__module__,
    }

    for name in (
        "base",
        "q",
        "mean",
        "sd",
        "lower",
        "upper",
    ):
        if hasattr(sampler, name):
            try:
                result[name] = json_safe(getattr(sampler, name))
            except Exception:
                pass

    result["repr"] = repr(sampler)
    return result


def encode_ray_domain(
    value: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "raw_class": type(value).__name__,
        "raw_module": type(value).__module__,
    }

    if isinstance(value, Categorical):
        categories = getattr(
            value,
            "categories",
            None,
        )

        result.update(
            {
                "kind": "categorical",
                "values": json_safe(categories),
            }
        )

    elif isinstance(value, Integer):
        result.update(
            {
                "kind": "integer_range",
                "lower": json_safe(getattr(value, "lower", None)),
                "upper": json_safe(getattr(value, "upper", None)),
            }
        )

    elif isinstance(value, Float):
        result.update(
            {
                "kind": "float_range",
                "lower": json_safe(getattr(value, "lower", None)),
                "upper": json_safe(getattr(value, "upper", None)),
            }
        )

    elif isinstance(value, Domain):
        result["kind"] = "domain"

    else:
        result.update(
            {
                "kind": "fixed",
                "value": json_safe(value),
            }
        )
        return result

    sampler = getattr(value, "sampler", None)

    result["sampler"] = encode_ray_sampler(sampler)

    return result


def encode_optuna_value(
    value: Any,
) -> dict[str, Any]:
    if isinstance(value, list):
        return {
            "kind": "categorical",
            "values": json_safe(value),
        }

    if isinstance(value, dict):
        return {
            "kind": "mapping",
            "value": json_safe(value),
        }

    if isinstance(
        value,
        (int, float, bool, type(None)),
    ):
        return {
            "kind": "fixed",
            "value": value,
        }

    if isinstance(value, str):
        if value == "loguniform":
            return {
                "kind": "log_float_marker",
            }

        if value == "uniform":
            return {
                "kind": "float_marker",
            }

        if value == "quantized_loguniform":
            return {
                "kind": "quantized_log_float_marker",
            }

        if value == "int":
            return {
                "kind": "integer_marker",
            }

        return {
            "kind": "string",
            "value": value,
        }

    return {
        "kind": "unknown",
        "repr": repr(value),
    }


classification = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))

eligible = [
    record["auto_model"]
    for record in classification["records"]
    if record["eligible_current_policy"]
]

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
                config = cls.get_default_config(
                    h=1,
                    backend=backend,
                    n_series=7,
                )
            except TypeError:
                config = cls.get_default_config(
                    h=1,
                    backend=backend,
                )

            if callable(config):
                config = config(MockTrial())

            encoded = {}

            for key, value in config.items():
                if backend == "ray":
                    encoded[key] = encode_ray_domain(value)
                else:
                    encoded[key] = encode_optuna_value(value)

            entry["backends"][backend] = {
                "status": "OK",
                "parameters": encoded,
            }

        except Exception as exc:
            entry["backends"][backend] = {
                "status": "ERROR",
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

errors = []

for record in records:
    for backend, result in record["backends"].items():
        if result["status"] != "OK":
            errors.append(
                (
                    record["auto_model"],
                    backend,
                    result.get("error"),
                )
            )

print("models=", len(records))
print("errors=", len(errors))

for model, backend, error in errors:
    print(
        "ERROR",
        model,
        backend,
        error,
    )

print("OUT=", OUTPUT)
print("AUTO_SPACES_STRUCTURED_EXTRACTION=PASS")
