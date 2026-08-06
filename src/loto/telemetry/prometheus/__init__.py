"""Strict low-cardinality Prometheus metric catalog and isolated collectors."""
from .catalog import (
    ARTIFACT_TYPE_LABELS,
    COLUMN_GROUP_LABELS,
    DATA_ROLE_LABELS,
    DeviceLabel,
    GameLabel,
    HorizonLabel,
    MetricValuePolicy,
    PlatformMetricCatalog,
    PlatformMetricSpec,
    SplitLabel,
    default_platform_metric_catalog,
    horizon_label,
)
from .registry import MetricUpdate, PrometheusMetricSet

__all__ = [
    "ARTIFACT_TYPE_LABELS",
    "COLUMN_GROUP_LABELS",
    "DATA_ROLE_LABELS",
    "DeviceLabel",
    "GameLabel",
    "HorizonLabel",
    "MetricUpdate",
    "MetricValuePolicy",
    "PlatformMetricCatalog",
    "PlatformMetricSpec",
    "PrometheusMetricSet",
    "SplitLabel",
    "default_platform_metric_catalog",
    "horizon_label",
]
