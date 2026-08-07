"""Evaluation protocol, metric, baseline, and seed aggregation contracts."""

from loto.evaluation.metric_registry import (
    BASELINE_REGISTRY,
    METRIC_REGISTRY,
    PRIMARY_METRIC_ID,
    REQUIRED_BASELINE_IDS,
    REQUIRED_POINT_METRICS,
    resolve_metric_id,
)
from loto.evaluation.protocol_diff import (
    ProtocolComparisonRefused,
    ProtocolDiff,
    ProtocolDifference,
)
from loto.evaluation.protocol_v2 import (
    EvaluationProtocolV2,
    LegacyProtocolV1,
    assert_protocols_comparable,
    compare_protocols,
    read_protocol_artifact,
    write_protocol_artifact,
)
from loto.evaluation.seed_summary import SeedMetricValue, SeedSummary, summarize_seed_metric
from loto.evaluation.selection import CandidateMetrics, select_by_primary_metric

__all__ = [
    "BASELINE_REGISTRY",
    "METRIC_REGISTRY",
    "PRIMARY_METRIC_ID",
    "REQUIRED_BASELINE_IDS",
    "REQUIRED_POINT_METRICS",
    "CandidateMetrics",
    "EvaluationProtocolV2",
    "LegacyProtocolV1",
    "ProtocolComparisonRefused",
    "ProtocolDiff",
    "ProtocolDifference",
    "SeedMetricValue",
    "SeedSummary",
    "assert_protocols_comparable",
    "compare_protocols",
    "read_protocol_artifact",
    "resolve_metric_id",
    "select_by_primary_metric",
    "summarize_seed_metric",
    "write_protocol_artifact",
]
