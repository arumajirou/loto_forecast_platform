"""StatsForecast-specific runtime bridge for real-game evaluation.

This module keeps Phase C on the already-certified constructor parameter contract while
leaving the generic :class:`loto.models.workers.PositionSeriesWorker` unchanged.  The
real-game campaign can therefore resolve every StatsForecast model deterministically before
handing it to the existing worker implementation.
"""

from __future__ import annotations

import importlib
from enum import StrEnum
from typing import Any

from loto.models.catalog import ModelSpec
from loto.models.workers import PositionSeriesWorker, WorkerOutput

from .model_parameters import resolve_parameters


class RealGameLane(StrEnum):
    """Scientific lane for one StatsForecast model in the primary campaign."""

    UNIVARIATE = "UNIVARIATE"
    EXOGENOUS = "EXOGENOUS"
    EXPECTED_NEGATIVE_CONTROL = "EXPECTED_NEGATIVE_CONTROL"


def lane_for_model(model_name: str) -> RealGameLane:
    """Return the non-overlapping evaluation lane for ``model_name``."""

    if model_name == "NaNModel":
        return RealGameLane.EXPECTED_NEGATIVE_CONTROL
    if model_name == "SklearnModel":
        return RealGameLane.EXOGENOUS
    return RealGameLane.UNIVARIATE


def resolve_entry_parameters(
    entry: Any,
    models_module: Any,
) -> dict[str, Any]:
    """Resolve the certified constructor parameters for a StatsForecast catalog entry."""

    if entry.library != "statsforecast":
        raise ValueError(f"expected statsforecast entry, got library={entry.library!r}")

    model_class = getattr(models_module, entry.class_name)
    parameters, unresolved = resolve_parameters(
        entry.class_name,
        model_class,
        dict(entry.default_params),
    )
    if unresolved:
        raise ValueError(
            "unresolved StatsForecast constructor parameters for "
            f"{entry.class_name}: {unresolved}"
        )
    return parameters


def resolved_model_spec(entry: Any, parameters: dict[str, Any]) -> ModelSpec:
    """Project a broad-catalog StatsForecast entry into the worker contract."""

    return ModelSpec(
        model_id=entry.model_id,
        family=entry.family,
        library=entry.library,
        task="position_series" if entry.task == "position" else entry.task,
        class_name=entry.class_name,
        priority=entry.priority,
        package=entry.package,
        capabilities=entry.capabilities,
        default_params=dict(parameters),
        notes=entry.notes,
    )


def forecast_univariate_entry(
    entry: Any,
    history: Any,
    *,
    position_columns: list[str],
    seed: int = 1,
    device: str = "cpu",
    precision: str = "32",
    models_module: Any | None = None,
    worker_class: type[PositionSeriesWorker] = PositionSeriesWorker,
) -> WorkerOutput:
    """Forecast one primary univariate StatsForecast entry with certified parameters.

    ``NaNModel`` and ``SklearnModel`` are deliberately not coerced into this lane.  Callers
    retain their model-game rows and record the semantic lane instead of silently dropping
    or misclassifying them.
    """

    lane = lane_for_model(entry.class_name)
    if lane is not RealGameLane.UNIVARIATE:
        raise ValueError(
            f"{entry.class_name} belongs to real-game lane {lane.value}, not UNIVARIATE"
        )

    if models_module is None:
        models_module = importlib.import_module("statsforecast.models")

    parameters = resolve_entry_parameters(entry, models_module)
    spec = resolved_model_spec(entry, parameters)
    return worker_class(
        spec,
        parameters,
        seed=seed,
        device=device,
        precision=precision,
        position_columns=position_columns,
    ).forecast(history)


__all__ = [
    "RealGameLane",
    "forecast_univariate_entry",
    "lane_for_model",
    "resolve_entry_parameters",
    "resolved_model_spec",
]
