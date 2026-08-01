from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OPTUNA_SOURCE = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_optuna_trial_calls.json"
)

COMPARISON_SOURCE = Path(
    "artifacts/parameter_inventory/"
    "neuralforecast_auto_structured_space_comparison.json"
)

OUTPUT = Path(
    "configs/generated/"
    "neuralforecast_normalized_fair_spaces.json"
)


def normalize_categorical(
    values: list[Any],
) -> list[Any]:
    """Remove duplicate choices while preserving order."""
    result: list[Any] = []

    for value in values:
        if value not in result:
            result.append(value)

    return result


optuna_records = json.loads(
    OPTUNA_SOURCE.read_text(encoding="utf-8")
)

comparison_records = json.loads(
    COMPARISON_SOURCE.read_text(encoding="utf-8")
)

comparison_by_model = {
    record["auto_model"]: record
    for record in comparison_records
}

models: dict[str, Any] = {}

for record in optuna_records:
    model = record["auto_model"]

    if record["status"] != "OK":
        continue

    comparison = comparison_by_model[model]

    ray_effective_by_parameter = {
        item["parameter"]: item["ray"]
        for item in comparison["parameters"]
    }

    parameters: dict[str, Any] = {}

    for call in record["trial_calls"]:
        name = call["parameter"]
        kind = call["kind"]

        if kind == "categorical":
            parameters[name] = {
                "kind": "categorical",
                "values": normalize_categorical(
                    call["choices"]
                ),
            }
            continue

        if kind in {
            "float",
            "log_float",
            "discrete_float",
        }:
            parameters[name] = {
                "kind": kind,
                "lower": call["low"],
                "upper": call["high"],
                "step": call.get("step"),
                "log": call.get("log", False),
            }
            continue

        if kind in {
            "integer",
            "log_int",
        }:
            ray_value = ray_effective_by_parameter.get(
                name,
                {},
            )

            optuna_lower = call["low"]
            optuna_upper = call["high"]

            ray_lower = ray_value.get(
                "lower",
                optuna_lower,
            )
            ray_upper = ray_value.get(
                "upper",
                optuna_upper,
            )

            common_lower = max(
                optuna_lower,
                ray_lower,
            )
            common_upper = min(
                optuna_upper,
                ray_upper,
            )

            if common_lower > common_upper:
                raise ValueError(
                    f"No common integer range for "
                    f"{model}.{name}: "
                    f"Optuna={optuna_lower}..{optuna_upper}, "
                    f"Ray={ray_lower}..{ray_upper}"
                )

            parameters[name] = {
                "kind": kind,
                "lower": common_lower,
                "upper": common_upper,
                "step": call.get("step", 1),
                "log": call.get("log", False),
                "normalization": (
                    "intersection_of_optuna_and_ray"
                ),
                "official_optuna_upper": optuna_upper,
                "official_ray_effective_upper": ray_upper,
            }
            continue

        raise ValueError(
            f"Unsupported kind: {model}.{name}={kind}"
        )

    models[model] = {
        "source": (
            "intersection_of_neuralforecast_"
            "optuna_and_ray_defaults"
        ),
        "parameters": parameters,
    }


payload = {
    "metadata": {
        "neuralforecast_version": "3.2.0",
        "model_count": len(models),
        "purpose": (
            "Backend-neutral fair comparison space"
        ),
        "integer_upper_policy": (
            "Intersection of Optuna inclusive and "
            "Ray effective exclusive ranges"
        ),
        "categorical_duplicate_policy": (
            "Remove duplicates preserving order"
        ),
    },
    "models": models,
}

OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT.write_text(
    json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

integer_parameters = [
    (model, name, value)
    for model, model_spec in models.items()
    for name, value
    in model_spec["parameters"].items()
    if value["kind"] in {
        "integer",
        "log_int",
    }
]

duplicate_normalized = [
    (model, name, value["values"])
    for model, model_spec in models.items()
    for name, value
    in model_spec["parameters"].items()
    if (
        value["kind"] == "categorical"
        and name == "step_size"
    )
]

print("models=", len(models))
print(
    "integer_parameters=",
    len(integer_parameters),
)
print(
    "step_size_parameters=",
    len(duplicate_normalized),
)

print("\n=== NORMALIZED INTEGER RANGES ===")
for model, name, value in integer_parameters:
    print(
        model,
        name,
        f"{value['lower']}..{value['upper']}",
    )

print("\n=== NORMALIZED STEP SIZE ===")
for model, name, values in duplicate_normalized:
    print(model, name, values)

print("OUT=", OUTPUT)
print("NORMALIZED_FAIR_SPACES=PASS")
