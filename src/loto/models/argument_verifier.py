from __future__ import annotations

from typing import Any

VERIFY_ARGUMENTS = (
    "input_size",
    "context_length",
    "h",
    "horizon",
    "max_steps",
    "epochs",
    "batch_size",
    "learning_rate",
    "hidden_size",
    "layers",
    "heads",
    "dropout",
    "lags",
    "n_series",
    "precision",
    "device",
    "backend",
    "num_samples",
    "parallel_trials",
    "cpus",
    "gpus",
    "seed",
)


def _read_effective(argument: str, properties: dict[str, Any]) -> Any:
    aliases = {
        "h": "horizon",
        "seed": "random_seed",
    }
    effective_parameters = properties.get("effective_parameters", {})
    if isinstance(effective_parameters, dict):
        for name in (argument, aliases.get(argument, argument)):
            if name in effective_parameters:
                return effective_parameters[name]
    return properties.get(argument, properties.get(aliases.get(argument, argument)))


def merge_effective_properties(
    *property_sets: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge property snapshots while ignoring NOT_EXPOSED placeholders.

    Later lifecycle snapshots take precedence only when they expose a concrete
    value. Nested ``effective_parameters`` dictionaries are merged separately.
    """

    merged: dict[str, Any] = {}
    merged_effective: dict[str, Any] = {}

    for properties in property_sets:
        if not isinstance(properties, dict):
            continue

        effective = properties.get("effective_parameters")
        if isinstance(effective, dict):
            for key, value in effective.items():
                if not (
                    isinstance(value, dict)
                    and value.get("status") == "NOT_EXPOSED"
                ):
                    merged_effective[key] = value

        for key, value in properties.items():
            if key == "effective_parameters":
                continue
            if (
                isinstance(value, dict)
                and value.get("status") == "NOT_EXPOSED"
            ):
                continue
            merged[key] = value

    if merged_effective:
        merged["effective_parameters"] = merged_effective

    return merged


def verify_arguments(
    requested: dict[str, Any],
    constructor_values: dict[str, Any],
    effective_properties: dict[str, Any],
    *,
    arguments: tuple[str, ...] = VERIFY_ARGUMENTS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordered_arguments = list(arguments)
    for argument in sorted(set(requested) | set(constructor_values)):
        if argument not in ordered_arguments:
            ordered_arguments.append(argument)
    for argument in ordered_arguments:
        if argument not in requested and argument not in constructor_values:
            rows.append({
                "argument": argument,
                "requested": None,
                "constructor_value": None,
                "effective_value": None,
                "evidence": [],
                "status": "UNSUPPORTED",
            })
            continue
        requested_value = requested.get(argument)
        constructor_value = constructor_values.get(argument, requested_value)
        effective_value = _read_effective(argument, effective_properties)
        evidence = ["requested_arguments.json", "resolved_config.yaml"]
        if argument in constructor_values:
            evidence.append("constructor_kwargs")
        if effective_value is not None:
            evidence.append("properties_after_fit.json")
        if isinstance(effective_value, dict) and effective_value.get("status") == "NOT_EXPOSED":
            status = "NOT_EXPOSED"
        elif effective_value == constructor_value == requested_value:
            status = "VERIFIED"
        elif effective_value == constructor_value and requested_value is None:
            status = "DEFAULTED"
        elif effective_value is None:
            status = "NOT_EXPOSED"
        elif constructor_value != requested_value:
            status = "TRANSFORMED"
        else:
            status = "IGNORED"
        rows.append({
            "argument": argument,
            "requested": requested_value,
            "constructor_value": constructor_value,
            "effective_value": effective_value,
            "evidence": evidence,
            "status": status,
        })
    return rows
