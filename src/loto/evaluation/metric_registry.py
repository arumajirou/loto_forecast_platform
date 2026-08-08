"""Canonical evaluation metric and baseline inventories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Iterable, Mapping


class MetricDirection(StrEnum):
    """Optimization direction for a metric."""

    MAXIMIZE = "MAXIMIZE"
    MINIMIZE = "MINIMIZE"


class MetricScope(StrEnum):
    """Scientific scope of a metric."""

    OVERALL = "OVERALL"
    POSITION = "POSITION"
    ALL_POSITIONS = "ALL_POSITIONS"


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """One canonical metric definition and its explicit legacy aliases."""

    metric_id: str
    display_name: str
    direction: MetricDirection
    scope: MetricScope
    aggregation: str
    required_for_point: bool
    required_for_probabilistic: bool
    legacy_aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BaselineDefinition:
    """One required baseline family."""

    baseline_id: str
    display_name: str
    deterministic: bool
    requires_seed: bool


_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        metric_id="hit_at_1",
        display_name="Hit@±1",
        direction=MetricDirection.MAXIMIZE,
        scope=MetricScope.OVERALL,
        aggregation="element_mean",
        required_for_point=True,
        required_for_probabilistic=True,
        legacy_aliases=("within_1_rate", "element_within_1", "mean_within_1"),
    ),
    MetricDefinition(
        metric_id="position_hit_at_1",
        display_name="Position Hit@±1",
        direction=MetricDirection.MAXIMIZE,
        scope=MetricScope.POSITION,
        aggregation="per_position_mean",
        required_for_point=True,
        required_for_probabilistic=True,
        legacy_aliases=("position_within_1",),
    ),
    MetricDefinition(
        metric_id="all_positions_hit_at_1",
        display_name="All-position Hit@±1",
        direction=MetricDirection.MAXIMIZE,
        scope=MetricScope.ALL_POSITIONS,
        aggregation="row_all",
        required_for_point=True,
        required_for_probabilistic=True,
        legacy_aliases=("row_within_1",),
    ),
    MetricDefinition(
        metric_id="mae",
        display_name="MAE",
        direction=MetricDirection.MINIMIZE,
        scope=MetricScope.OVERALL,
        aggregation="element_mean",
        required_for_point=True,
        required_for_probabilistic=True,
        legacy_aliases=("position_mae",),
    ),
    MetricDefinition(
        metric_id="mse",
        display_name="MSE",
        direction=MetricDirection.MINIMIZE,
        scope=MetricScope.OVERALL,
        aggregation="element_mean",
        required_for_point=True,
        required_for_probabilistic=True,
        legacy_aliases=("position_mse",),
    ),
    MetricDefinition(
        metric_id="rmse",
        display_name="RMSE",
        direction=MetricDirection.MINIMIZE,
        scope=MetricScope.OVERALL,
        aggregation="sqrt_element_mean",
        required_for_point=True,
        required_for_probabilistic=True,
        legacy_aliases=("position_rmse",),
    ),
)

METRIC_REGISTRY: Final[Mapping[str, MetricDefinition]] = MappingProxyType(
    {item.metric_id: item for item in _METRICS}
)

_ALIAS_TO_CANONICAL: Final[Mapping[str, str]] = MappingProxyType(
    {alias: item.metric_id for item in _METRICS for alias in (item.metric_id, *item.legacy_aliases)}
)

PRIMARY_METRIC_ID: Final[str] = "hit_at_1"
REQUIRED_POINT_METRICS: Final[tuple[str, ...]] = tuple(
    item.metric_id for item in _METRICS if item.required_for_point
)

_REQUIRED_BASELINES: tuple[BaselineDefinition, ...] = (
    BaselineDefinition("random", "Random", deterministic=False, requires_seed=True),
    BaselineDefinition("fixed", "Fixed value", deterministic=True, requires_seed=False),
    BaselineDefinition("mean", "Mean", deterministic=True, requires_seed=False),
    BaselineDefinition("median", "Median", deterministic=True, requires_seed=False),
    BaselineDefinition("last", "Last value", deterministic=True, requires_seed=False),
    BaselineDefinition("frequency", "Frequency", deterministic=True, requires_seed=False),
    BaselineDefinition(
        "statistical_ar1",
        "Statistical AR(1)",
        deterministic=True,
        requires_seed=False,
    ),
)

BASELINE_REGISTRY: Final[Mapping[str, BaselineDefinition]] = MappingProxyType(
    {item.baseline_id: item for item in _REQUIRED_BASELINES}
)
REQUIRED_BASELINE_IDS: Final[tuple[str, ...]] = tuple(BASELINE_REGISTRY)


def resolve_metric_id(metric_name: str) -> str:
    """Resolve a canonical metric ID or an explicit legacy alias."""

    try:
        return _ALIAS_TO_CANONICAL[metric_name]
    except KeyError as exc:
        raise KeyError(f"unknown metric name or alias: {metric_name!r}") from exc


def metric_definition(metric_name: str) -> MetricDefinition:
    """Return the canonical definition for ``metric_name``."""

    return METRIC_REGISTRY[resolve_metric_id(metric_name)]


def canonicalize_metric_values(values: Mapping[str, float]) -> dict[str, float]:
    """Canonicalize metric keys and reject conflicting aliases."""

    canonical: dict[str, float] = {}
    for key, value in values.items():
        metric_id = resolve_metric_id(key)
        numeric = float(value)
        if metric_id in canonical and canonical[metric_id] != numeric:
            raise ValueError(f"conflicting values supplied for canonical metric {metric_id!r}")
        canonical[metric_id] = numeric
    return canonical


def validate_metric_inventory(metric_ids: Iterable[str]) -> tuple[str, ...]:
    """Validate and canonicalize a metric inventory without duplicates."""

    resolved = tuple(resolve_metric_id(item) for item in metric_ids)
    if len(set(resolved)) != len(resolved):
        raise ValueError("metric inventory contains duplicate canonical metrics")
    missing = set(REQUIRED_POINT_METRICS).difference(resolved)
    if missing:
        raise ValueError(f"metric inventory is missing required metrics: {sorted(missing)}")
    return resolved
