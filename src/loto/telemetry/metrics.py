"""Exporter-neutral metric registry and strict cardinality policy."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.telemetry.contracts import Component, EventStatus

_METRIC_NAME_RE = re.compile(r"^loto_[a-z][a-z0-9_]{2,95}$")
_LABEL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
PROHIBITED_LABELS = frozenset(
    {
        "artifact_path",
        "config_hash",
        "dataset_hash",
        "error_message",
        "git_sha",
        "model_revision",
        "request_id",
        "run_id",
        "span_id",
        "trace_id",
        "user_id",
    }
)


class MetricKind(StrEnum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class MetricDefinition(BaseModel):
    """One bounded metric declaration; no exporter is created here."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )

    name: str
    kind: MetricKind
    description: str = Field(min_length=1, max_length=256)
    unit: str = Field(min_length=1, max_length=32)
    label_allowlist: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    buckets: tuple[float, ...] = ()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not _METRIC_NAME_RE.fullmatch(value):
            raise ValueError("metric name must use the loto_ snake_case namespace")
        return value

    @field_validator("label_allowlist")
    @classmethod
    def validate_labels(
        cls, value: dict[str, tuple[str, ...]]
    ) -> dict[str, tuple[str, ...]]:
        if len(value) > 5:
            raise ValueError("metric labels exceed the maximum of 5")
        for label, allowed in value.items():
            if not _LABEL_NAME_RE.fullmatch(label):
                raise ValueError(f"invalid metric label name: {label!r}")
            if label in PROHIBITED_LABELS:
                raise ValueError(f"high-cardinality/protected label is prohibited: {label}")
            if not allowed or len(allowed) > 64:
                raise ValueError(f"label {label!r} must have 1..64 approved values")
            if len(set(allowed)) != len(allowed):
                raise ValueError(f"label {label!r} contains duplicate approved values")
            if any(not item or len(item) > 64 for item in allowed):
                raise ValueError(f"label {label!r} contains an invalid approved value")
        return value

    @model_validator(mode="after")
    def validate_buckets(self) -> MetricDefinition:
        if self.kind is MetricKind.HISTOGRAM:
            if not self.buckets:
                raise ValueError("histogram metrics require reviewed buckets")
            if tuple(sorted(set(self.buckets))) != self.buckets:
                raise ValueError("histogram buckets must be unique and increasing")
        elif self.buckets:
            raise ValueError("only histogram metrics may define buckets")
        return self


class MetricRegistry:
    """Deterministic registry that rejects duplicate declarations and label drift."""

    def __init__(self) -> None:
        self._definitions: dict[str, MetricDefinition] = {}

    def register(self, definition: MetricDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"metric already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> MetricDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise KeyError(f"unknown metric: {name}") from exc

    def definitions(self) -> tuple[MetricDefinition, ...]:
        return tuple(self._definitions[name] for name in sorted(self._definitions))

    def validate_labels(self, name: str, labels: dict[str, str]) -> None:
        definition = self.get(name)
        expected = set(definition.label_allowlist)
        if set(labels) != expected:
            raise ValueError(
                f"metric {name} labels must be exactly {sorted(expected)}; got {sorted(labels)}"
            )
        for label, value in labels.items():
            if value not in definition.label_allowlist[label]:
                raise ValueError(f"metric {name} label {label} has unapproved value {value!r}")


def default_telemetry_metric_registry() -> MetricRegistry:
    """Return the exporter-neutral self-observation metric definitions."""

    registry = MetricRegistry()
    registry.register(
        MetricDefinition(
            name="loto_telemetry_events_total",
            kind=MetricKind.COUNTER,
            description="Structured telemetry events accepted by the local contract boundary.",
            unit="events",
            label_allowlist={
                "component": tuple(item.value for item in Component),
                "status": tuple(item.value for item in EventStatus),
            },
        )
    )
    registry.register(
        MetricDefinition(
            name="loto_telemetry_dropped_total",
            kind=MetricKind.COUNTER,
            description="Optional telemetry events dropped by bounded local buffering.",
            unit="events",
            label_allowlist={"reason": ("buffer_full", "invalid_event", "sink_unavailable")},
        )
    )
    registry.register(
        MetricDefinition(
            name="loto_telemetry_buffer_size",
            kind=MetricKind.GAUGE,
            description="Current number of events in the bounded local telemetry buffer.",
            unit="events",
        )
    )
    return registry
