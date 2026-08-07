"""All-seed aggregation for canonical evaluation metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean, pstdev, pvariance

from loto.evaluation.metric_registry import MetricDirection, metric_definition


@dataclass(frozen=True, slots=True)
class SeedMetricValue:
    """One seed's value for one metric."""

    seed: int
    value: float


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """Required all-seed aggregate."""

    metric_id: str
    count: int
    mean: float
    population_variance: float
    standard_deviation: float
    minimum: float
    maximum: float
    worst_value: float
    worst_seed: int

    def to_dict(self) -> dict[str, int | float | str]:
        """Return a JSON-compatible representation."""

        return {
            "metric_id": self.metric_id,
            "count": self.count,
            "mean": self.mean,
            "population_variance": self.population_variance,
            "standard_deviation": self.standard_deviation,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "worst_value": self.worst_value,
            "worst_seed": self.worst_seed,
        }


def summarize_seed_metric(
    metric_name: str,
    values: list[SeedMetricValue],
    *,
    expected_seeds: tuple[int, ...],
) -> SeedSummary:
    """Aggregate every expected seed and reject best-seed-only or partial input."""

    definition = metric_definition(metric_name)
    if not expected_seeds:
        raise ValueError("expected seed inventory must not be empty")
    if len(set(expected_seeds)) != len(expected_seeds):
        raise ValueError("expected seed inventory contains duplicates")
    by_seed: dict[int, float] = {}
    for item in values:
        if item.seed in by_seed:
            raise ValueError(f"duplicate metric value for seed {item.seed}")
        numeric = float(item.value)
        if not math.isfinite(numeric):
            raise ValueError("seed metric values must be finite")
        by_seed[item.seed] = numeric
    if set(by_seed) != set(expected_seeds):
        missing = sorted(set(expected_seeds).difference(by_seed))
        unexpected = sorted(set(by_seed).difference(expected_seeds))
        raise ValueError(
            "all approved seeds are required; "
            f"missing={missing}, unexpected={unexpected}"
        )
    ordered = [(seed, by_seed[seed]) for seed in expected_seeds]
    numeric_values = [value for _, value in ordered]
    if definition.direction is MetricDirection.MAXIMIZE:
        worst_seed, worst_value = min(ordered, key=lambda item: (item[1], item[0]))
    else:
        worst_seed, worst_value = max(ordered, key=lambda item: (item[1], -item[0]))
    return SeedSummary(
        metric_id=definition.metric_id,
        count=len(numeric_values),
        mean=float(fmean(numeric_values)),
        population_variance=float(pvariance(numeric_values)),
        standard_deviation=float(pstdev(numeric_values)),
        minimum=float(min(numeric_values)),
        maximum=float(max(numeric_values)),
        worst_value=float(worst_value),
        worst_seed=worst_seed,
    )
