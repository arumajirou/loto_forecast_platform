from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainDescription:
    key: str
    kind: str
    values: tuple[Any, ...]
    lower: float | int | None = None
    upper: float | int | None = None
    log: bool = False
    raw_repr: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "values": list(self.values),
            "lower": self.lower,
            "upper": self.upper,
            "log": self.log,
            "raw_repr": self.raw_repr,
        }


def _representative_numeric(lower: float, upper: float, *, log: bool) -> tuple[float, ...]:
    if lower == upper:
        return (lower,)
    quantiles = (0.0, 0.25, 0.5, 0.75, 1.0)
    if log and lower > 0 and upper > 0:
        lo = math.log(lower)
        hi = math.log(upper)
        return tuple(math.exp(lo + (hi - lo) * q) for q in quantiles)
    return tuple(lower + (upper - lower) * q for q in quantiles)


def describe_domain(key: str, value: Any) -> DomainDescription:
    raw = repr(value)
    categories = getattr(value, "categories", None)
    if categories is not None:
        return DomainDescription(key, "categorical", tuple(categories), raw_repr=raw)

    lower = getattr(value, "lower", None)
    upper = getattr(value, "upper", None)
    sampler = getattr(value, "sampler", None)
    sampler_name = type(sampler).__name__.lower() if sampler is not None else ""
    if lower is not None and upper is not None:
        is_integer = "integer" in type(value).__name__.lower()
        is_log = "log" in sampler_name
        points = _representative_numeric(float(lower), float(upper), log=is_log)
        if is_integer:
            # Ray randint upper bound is exclusive.
            hi = max(int(lower), int(upper) - 1)
            points = tuple(sorted({int(round(min(max(point, lower), hi))) for point in points}))
            return DomainDescription(key, "integer", points, int(lower), int(upper), is_log, raw)
        return DomainDescription(key, "float", points, float(lower), float(upper), is_log, raw)

    if isinstance(value, (list, tuple)):
        # Plain lists are model parameters (for example NHITS kernel vectors),
        # not search domains. Ray categorical domains are handled above.
        return DomainDescription(key, "constant_sequence", (value,), raw_repr=raw)
    return DomainDescription(key, "constant", (value,), raw_repr=raw)


def describe_config(config: dict[str, Any]) -> list[DomainDescription]:
    return [describe_domain(key, value) for key, value in sorted(config.items())]


def freeze_value(description: DomainDescription, *, strategy: str = "small") -> Any:
    values = description.values
    if not values:
        raise ValueError(f"domain has no representative values: {description.key}")
    if strategy == "small":
        if description.kind in {"integer", "float"}:
            return values[0]
        return values[0]
    if strategy == "median":
        return values[len(values) // 2]
    if strategy == "large":
        return values[-1]
    raise ValueError(f"unknown freeze strategy: {strategy}")


def freeze_config(
    config: dict[str, Any],
    *,
    strategy: str = "small",
    h: int,
    n_series: int | None,
    seed: int,
    smoke: bool,
    max_steps_smoke: int,
    val_check_steps_smoke: int,
    accelerator: str,
    devices: int,
    precision: str,
) -> dict[str, Any]:
    frozen = {
        description.key: freeze_value(description, strategy=strategy)
        for description in describe_config(config)
    }
    for protected in ("h", "loss", "valid_loss"):
        frozen.pop(protected, None)
    if n_series is not None:
        frozen["n_series"] = n_series
    frozen["random_seed"] = seed
    frozen.setdefault("input_size", max(1, h * 2))
    frozen.setdefault("step_size", 1)
    if smoke:
        frozen["max_steps"] = max_steps_smoke
        frozen["val_check_steps"] = val_check_steps_smoke
        frozen["early_stop_patience_steps"] = -1
        frozen["batch_size"] = max(1, min(int(frozen.get("batch_size", 1)), n_series or 5))
        frozen["windows_batch_size"] = max(1, min(int(frozen.get("windows_batch_size", 32)), 32))
        if "inference_windows_batch_size" in frozen:
            frozen["inference_windows_batch_size"] = max(
                1, min(int(frozen["inference_windows_batch_size"]), 32)
            )
    frozen.update(
        {
            "accelerator": accelerator,
            "devices": devices,
            "precision": precision,
            "enable_checkpointing": False,
            "enable_progress_bar": False,
            "logger": False,
            "deterministic": True,
            "benchmark": False,
            "num_sanity_val_steps": 0,
        }
    )
    return frozen


def add_random_representatives(
    descriptions: list[DomainDescription], *, count: int, seed: int
) -> dict[str, list[Any]]:
    rng = random.Random(seed)
    output: dict[str, list[Any]] = {}
    for description in descriptions:
        values = list(description.values)
        if (
            description.kind == "float"
            and description.lower is not None
            and description.upper is not None
        ):  # noqa: E501
            for _ in range(count):
                if description.log and description.lower > 0:
                    value = math.exp(
                        rng.uniform(math.log(description.lower), math.log(description.upper))
                    )
                else:
                    value = rng.uniform(float(description.lower), float(description.upper))
                values.append(value)
        elif (
            description.kind == "integer"
            and description.lower is not None
            and description.upper is not None
        ):  # noqa: E501
            hi = max(int(description.lower), int(description.upper) - 1)
            values.extend(rng.randint(int(description.lower), hi) for _ in range(count))
        deduped: dict[str, Any] = {}
        for value in values:
            key = json.dumps(value, sort_keys=True, ensure_ascii=False, default=repr)
            deduped.setdefault(key, value)
        output[description.key] = list(deduped.values())
    return output
