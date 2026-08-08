"""Dependency-light evidence for NeuralForecast AutoModel search spaces."""

from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict


class SearchSpaceCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class SearchSpaceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    model_name: str | None = None
    backend: str
    source: str
    completeness: SearchSpaceCompleteness
    dimensions: tuple[dict[str, Any], ...] = ()
    tunable_count: int = 0
    constant_count: int = 0
    categorical_count: int = 0
    integer_count: int = 0
    continuous_count: int = 0
    conditional: bool | None = False
    finite_combination_count: int | None = None
    cmaes_eligible: bool = False
    grid_eligible: bool = False
    probe_errors: tuple[str, ...] = ()
    profile_sha256: str = ""

    def model_post_init(self, _: Any) -> None:
        if self.profile_sha256:
            return
        payload = self.model_dump(mode="json", exclude={"profile_sha256"})
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "profile_sha256", hashlib.sha256(raw).hexdigest())


def _finish(
    *,
    backend: str,
    source: str,
    completeness: SearchSpaceCompleteness,
    dimensions: list[dict[str, Any]],
    model_name: str | None,
    conditional: bool | None = False,
    errors: tuple[str, ...] = (),
) -> SearchSpaceProfile:
    kinds = [item["kind"] for item in dimensions]
    cards = [item.get("cardinality") for item in dimensions]
    combinations = None if any(card is None for card in cards) else math.prod(cards)
    tunable = sum(kind != "constant" for kind in kinds)
    categorical = kinds.count("categorical")
    complete = completeness is SearchSpaceCompleteness.COMPLETE
    return SearchSpaceProfile(
        model_name=model_name,
        backend=backend,
        source=source,
        completeness=completeness,
        dimensions=tuple(sorted(dimensions, key=lambda item: item["name"])),
        tunable_count=tunable,
        constant_count=kinds.count("constant"),
        categorical_count=categorical,
        integer_count=kinds.count("integer"),
        continuous_count=kinds.count("float"),
        conditional=conditional,
        finite_combination_count=combinations,
        cmaes_eligible=(
            backend == "optuna"
            and complete
            and tunable > 0
            and categorical == 0
            and not conditional
        ),
        grid_eligible=(
            complete and combinations is not None and 1 < combinations <= 256 and not conditional
        ),
        probe_errors=errors,
    )


def _constant(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, (type(None), bool, int, float, str, list, tuple)):
        value = repr(value)
    return {"name": name, "kind": "constant", "value": value, "cardinality": 1}


def profile_fixed_config(
    config: dict[str, Any], *, backend: str, model_name: str | None = None
) -> SearchSpaceProfile:
    return _finish(
        backend=backend,
        source="fixed_config",
        completeness=SearchSpaceCompleteness.COMPLETE,
        dimensions=[_constant(name, value) for name, value in config.items()],
        model_name=model_name,
    )


def profile_ray_config(
    config: dict[str, Any], *, model_name: str | None = None
) -> SearchSpaceProfile:
    dimensions: list[dict[str, Any]] = []
    for name, value in config.items():
        categories = getattr(value, "categories", None)
        if categories is not None:
            values = list(categories)
            dimensions.append(
                {
                    "name": name,
                    "kind": "categorical",
                    "choices": values,
                    "cardinality": len(values),
                }
            )
            continue
        low, high = getattr(value, "lower", None), getattr(value, "upper", None)
        if low is None or high is None:
            dimensions.append(_constant(name, value))
            continue
        integer = "integer" in type(value).__name__.lower()
        dimensions.append(
            {
                "name": name,
                "kind": "integer" if integer else "float",
                "lower": low,
                "upper": high,
                "upper_inclusive": not integer,
                "cardinality": max(0, int(high) - int(low)) if integer else None,
            }
        )
    return _finish(
        backend="ray",
        source="ray_domain_introspection",
        completeness=SearchSpaceCompleteness.COMPLETE,
        dimensions=dimensions,
        model_name=model_name,
    )


class _Trial:
    def __init__(self, number: int, mode: str):
        self.number = number
        self.mode = mode
        self.dimensions: dict[str, dict[str, Any]] = {}

    def _pick(self, values: list[Any]) -> Any:
        if self.mode == "low":
            return values[0]
        if self.mode == "high":
            return values[-1]
        return values[len(values) // 2]

    def suggest_categorical(self, name: str, choices: list[Any]) -> Any:
        self.dimensions[name] = {
            "name": name,
            "kind": "categorical",
            "choices": choices,
            "cardinality": len(choices),
        }
        return self._pick(choices)

    def suggest_int(
        self, name: str, low: int, high: int, *, step: int = 1, log: bool = False
    ) -> int:
        self.dimensions[name] = {
            "name": name,
            "kind": "integer",
            "lower": low,
            "upper": high,
            "step": step,
            "log": log,
            "cardinality": (high - low) // step + 1,
        }
        return int(self._pick(list(range(low, high + 1, step))))

    def suggest_float(
        self, name: str, low: float, high: float, *, step: float | None = None, log: bool = False
    ) -> float:
        card = int(math.floor((high - low) / step)) + 1 if step else None
        self.dimensions[name] = {
            "name": name,
            "kind": "float",
            "lower": low,
            "upper": high,
            "step": step,
            "log": log,
            "cardinality": card,
        }
        if self.mode == "low":
            return low
        if self.mode == "high":
            return high
        return math.sqrt(low * high) if log and low > 0 else (low + high) / 2


def profile_optuna_config(
    config: Callable[[Any], dict[str, Any]], *, model_name: str | None = None
) -> SearchSpaceProfile:
    probes: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
    errors: list[str] = []
    for number, mode in enumerate(("low", "middle", "high")):
        trial = _Trial(number, mode)
        try:
            result = config(trial)
            if not isinstance(result, dict):
                raise TypeError("config did not return a dict")
            probes.append((result, trial.dimensions))
        except Exception as exc:
            errors.append(f"probe={number}:{type(exc).__name__}:{exc}")
    if not probes:
        return _finish(
            backend="optuna",
            source="optuna_recording_trial",
            completeness=SearchSpaceCompleteness.FAILED,
            dimensions=[],
            model_name=model_name,
            conditional=None,
            errors=tuple(errors),
        )
    names = sorted({name for _, dimensions in probes for name in dimensions})
    dimensions = [next(items[name] for _, items in probes if name in items) for name in names]
    key_sets = {tuple(sorted(result)) for result, _ in probes}
    observed = {name: sum(name in items for _, items in probes) for name in names}
    conditional = len(key_sets) > 1 or any(count != len(probes) for count in observed.values())
    return _finish(
        backend="optuna",
        source="optuna_recording_trial",
        completeness=SearchSpaceCompleteness.PARTIAL,
        dimensions=dimensions,
        model_name=model_name,
        conditional=conditional,
        errors=tuple(errors),
    )


def unavailable_search_space_profile(
    *, backend: str, model_name: str | None, reason: str
) -> SearchSpaceProfile:
    return _finish(
        backend=backend,
        source="unavailable",
        completeness=SearchSpaceCompleteness.UNAVAILABLE,
        dimensions=[],
        model_name=model_name,
        conditional=None,
        errors=(reason,),
    )


def profile_runtime_model_config(
    model: Any, *, backend: str, model_name: str | None, fallback: SearchSpaceProfile | None = None
) -> SearchSpaceProfile:
    config = getattr(model, "config", None)
    if isinstance(config, dict):
        if backend == "ray":
            return profile_ray_config(config, model_name=model_name)
        return profile_fixed_config(config, backend=backend, model_name=model_name)
    if callable(config) and backend == "optuna":
        return profile_optuna_config(config, model_name=model_name)
    return fallback or unavailable_search_space_profile(
        backend=backend, model_name=model_name, reason="runtime config unavailable"
    )


def write_search_space_profile(
    directory: str | Path, profile: SearchSpaceProfile
) -> dict[str, str]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(
            profile.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, indent=2
        ).encode()
        + b"\n"
    )
    digest = hashlib.sha256(content).hexdigest()
    files = [
        (root / "SEARCH_SPACE_PROFILE.json", content),
        (root / "SEARCH_SPACE_PROFILE.sha256", f"{digest}  SEARCH_SPACE_PROFILE.json\n".encode()),
    ]
    for path, data in files:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)
    return {"path": str(files[0][0]), "sha256_path": str(files[1][0]), "sha256": digest}
