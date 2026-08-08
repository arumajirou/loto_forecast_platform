"""Canonical model selection using Hit@±1 before error metrics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from loto.evaluation.metric_registry import canonicalize_metric_values


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    """Metrics used by the canonical deterministic ordering policy."""

    model_id: str
    metrics: Mapping[str, float]


def _finite(value: float, name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"metric {name!r} must be finite")
    return numeric


def select_by_primary_metric(candidates: Sequence[CandidateMetrics]) -> CandidateMetrics:
    """Select by Hit@±1, then all-position Hit@±1, MAE, RMSE, and model ID.

    This ordering intentionally prevents a lower-MAE candidate from winning when its
    canonical primary Hit@±1 value is worse.
    """

    if not candidates:
        raise ValueError("at least one candidate is required")

    def key(candidate: CandidateMetrics) -> tuple[float, float, float, float, str]:
        values = canonicalize_metric_values(candidate.metrics)
        required = ("hit_at_1", "all_positions_hit_at_1", "mae", "rmse")
        missing = [metric_id for metric_id in required if metric_id not in values]
        if missing:
            raise ValueError(f"candidate {candidate.model_id!r} is missing metrics: {missing}")
        hit = _finite(values["hit_at_1"], "hit_at_1")
        all_hit = _finite(values["all_positions_hit_at_1"], "all_positions_hit_at_1")
        mae = _finite(values["mae"], "mae")
        rmse = _finite(values["rmse"], "rmse")
        return (-hit, -all_hit, mae, rmse, candidate.model_id)

    return min(candidates, key=key)
