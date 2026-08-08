"""Concrete isolated Prometheus collectors with strict validation."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, ConfigDict, Field

from loto.telemetry.metrics import MetricKind
from loto.telemetry.prometheus.catalog import (
    PlatformMetricCatalog,
    default_platform_metric_catalog,
)


class MetricUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )

    name: str = Field(min_length=1, max_length=128)
    value: float
    labels: dict[str, str] = Field(default_factory=dict)


class PrometheusMetricSet:
    """One isolated collector set; never touches the global registry."""

    def __init__(
        self,
        catalog: PlatformMetricCatalog | None = None,
        *,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self.catalog = catalog if catalog is not None else default_platform_metric_catalog()
        self.registry = registry if registry is not None else CollectorRegistry(auto_describe=True)
        self._collectors: dict[str, Counter | Gauge | Histogram] = {}
        for spec in self.catalog.specs():
            definition = spec.definition
            labelnames = tuple(definition.label_allowlist)
            if definition.kind is MetricKind.COUNTER:
                collector: Counter | Gauge | Histogram = Counter(
                    definition.name,
                    definition.description,
                    labelnames=labelnames,
                    registry=self.registry,
                )
            elif definition.kind is MetricKind.GAUGE:
                collector = Gauge(
                    definition.name,
                    definition.description,
                    labelnames=labelnames,
                    registry=self.registry,
                )
            else:
                collector = Histogram(
                    definition.name,
                    definition.description,
                    labelnames=labelnames,
                    buckets=definition.buckets,
                    registry=self.registry,
                )
            self._collectors[definition.name] = collector

    def _validate(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
        expected: MetricKind,
    ) -> tuple[Any, float]:
        spec = self.catalog.get(name)
        if spec.definition.kind is not expected:
            raise ValueError(f"metric {name} is {spec.definition.kind}, not {expected}")
        self.catalog.validate_labels(name, labels)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("metric value must be int or float")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("metric value must be finite")
        policy = spec.value_policy
        if policy.minimum is not None and numeric < policy.minimum:
            raise ValueError(f"metric {name} is below minimum {policy.minimum}")
        if policy.maximum is not None and numeric > policy.maximum:
            raise ValueError(f"metric {name} exceeds maximum {policy.maximum}")
        if policy.integer_only and not numeric.is_integer():
            raise ValueError(f"metric {name} requires an integer value")
        return self._collectors[name], numeric

    @staticmethod
    def _child(collector: Any, labels: dict[str, str]) -> Any:
        return collector.labels(**labels) if labels else collector

    def increment(
        self,
        name: str,
        amount: float = 1.0,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        normalized = labels or {}
        collector, numeric = self._validate(
            name,
            amount,
            normalized,
            MetricKind.COUNTER,
        )
        self._child(collector, normalized).inc(numeric)

    def set_gauge(
        self,
        name: str,
        value: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        normalized = labels or {}
        collector, numeric = self._validate(
            name,
            value,
            normalized,
            MetricKind.GAUGE,
        )
        self._child(collector, normalized).set(numeric)

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        normalized = labels or {}
        collector, numeric = self._validate(
            name,
            value,
            normalized,
            MetricKind.HISTOGRAM,
        )
        self._child(collector, normalized).observe(numeric)

    def validate_updates(
        self,
        updates: Iterable[tuple[MetricKind, MetricUpdate]],
    ) -> tuple[tuple[MetricKind, MetricUpdate], ...]:
        materialized = tuple(updates)
        for kind, update in materialized:
            self._validate(update.name, update.value, update.labels, kind)
        return materialized

    def apply_updates(
        self,
        updates: Iterable[tuple[MetricKind, MetricUpdate]],
    ) -> None:
        for kind, update in self.validate_updates(updates):
            if kind is MetricKind.COUNTER:
                self.increment(
                    update.name,
                    update.value,
                    labels=update.labels,
                )
            elif kind is MetricKind.GAUGE:
                self.set_gauge(
                    update.name,
                    update.value,
                    labels=update.labels,
                )
            else:
                self.observe(
                    update.name,
                    update.value,
                    labels=update.labels,
                )

    def render(self) -> bytes:
        return generate_latest(self.registry)

    def touched_series_count(self) -> int:
        return sum(len(family.samples) for family in self.registry.collect())
