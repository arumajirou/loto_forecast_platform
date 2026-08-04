from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OPTUNA_SOURCE = Path("artifacts/parameter_inventory/neuralforecast_optuna_trial_calls.json")

RAY_SOURCE = Path("artifacts/parameter_inventory/neuralforecast_auto_spaces_structured.json")

OUTPUT = Path("artifacts/parameter_inventory/neuralforecast_auto_structured_space_comparison.json")


def canonical_optuna(
    call: dict[str, Any],
) -> dict[str, Any]:
    kind = call["kind"]

    if kind == "categorical":
        values = call["choices"]

        return {
            "kind": "categorical",
            "values": values,
        }

    if kind in {
        "float",
        "log_float",
        "discrete_float",
    }:
        return {
            "kind": kind,
            "lower": call["low"],
            "upper": call["high"],
            "step": call.get("step"),
            "log": call.get("log", False),
        }

    if kind in {
        "integer",
        "log_int",
    }:
        return {
            "kind": kind,
            "lower": call["low"],
            "upper": call["high"],
            "step": call.get("step", 1),
            "log": call.get("log", False),
        }

    return call


def canonical_ray(
    value: dict[str, Any],
) -> dict[str, Any]:
    kind = value["kind"]

    if kind == "categorical":
        return {
            "kind": "categorical",
            "values": value.get("values"),
        }

    if kind == "integer_range":
        sampler = value.get("sampler") or {}
        sampler_class = sampler.get("class", "")

        raw_upper = value.get("upper")
        step = sampler.get("q", 1)

        # Ray Integer domains use an exclusive upper bound.
        effective_upper = raw_upper - step if raw_upper is not None else None

        return {
            "kind": ("log_int" if "LogUniform" in sampler_class else "integer"),
            "lower": value.get("lower"),
            "upper": effective_upper,
            "raw_upper_exclusive": raw_upper,
            "step": step,
            "log": "LogUniform" in sampler_class,
        }

    if kind == "float_range":
        sampler = value.get("sampler") or {}
        sampler_class = sampler.get("class", "")

        if sampler_class == "Quantized":
            result_kind = "discrete_float"
        elif "LogUniform" in sampler_class:
            result_kind = "log_float"
        else:
            result_kind = "float"

        return {
            "kind": result_kind,
            "lower": value.get("lower"),
            "upper": value.get("upper"),
            "step": sampler.get("q"),
            "log": "LogUniform" in sampler_class,
        }

    if kind == "fixed":
        return {
            "kind": "fixed",
            "value": value.get("value"),
        }

    return value


optuna_records = json.loads(OPTUNA_SOURCE.read_text(encoding="utf-8"))

ray_records = json.loads(RAY_SOURCE.read_text(encoding="utf-8"))

optuna_by_model = {record["auto_model"]: record for record in optuna_records}

ray_by_model = {record["auto_model"]: record for record in ray_records}

results = []

for model in sorted(set(optuna_by_model) | set(ray_by_model)):
    optuna_record = optuna_by_model.get(model, {})
    ray_record = ray_by_model.get(model, {})

    optuna_parameters = {
        call["parameter"]: canonical_optuna(call)
        for call in optuna_record.get(
            "trial_calls",
            [],
        )
    }

    ray_parameters_raw = ray_record.get("backends", {}).get("ray", {}).get("parameters", {})

    ray_parameters = {
        name: canonical_ray(value)
        for name, value in ray_parameters_raw.items()
        if name
        not in {
            "h",
            "loss",
        }
    }

    names = sorted(set(optuna_parameters) | set(ray_parameters))

    differences = []

    for name in names:
        optuna_value = optuna_parameters.get(
            name,
            "__MISSING__",
        )
        ray_value = ray_parameters.get(
            name,
            "__MISSING__",
        )

        equivalent = optuna_value == ray_value

        differences.append(
            {
                "parameter": name,
                "equivalent": equivalent,
                "optuna": optuna_value,
                "ray": ray_value,
            }
        )

    results.append(
        {
            "auto_model": model,
            "parameter_count": len(names),
            "equivalent_count": sum(item["equivalent"] for item in differences),
            "difference_count": sum(not item["equivalent"] for item in differences),
            "parameters": differences,
        }
    )

OUTPUT.write_text(
    json.dumps(
        results,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

for record in results:
    print(
        f"{record['auto_model']:28s}",
        "parameters=",
        record["parameter_count"],
        "equivalent=",
        record["equivalent_count"],
        "different=",
        record["difference_count"],
    )

print(
    "total_differences=",
    sum(record["difference_count"] for record in results),
)

print("OUT=", OUTPUT)
print("STRUCTURED_AUTO_SPACE_COMPARISON=PASS")
