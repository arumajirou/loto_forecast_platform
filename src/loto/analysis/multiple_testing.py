"""Deterministic family-level multiple-testing correction."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from loto.analysis.contracts import AdjustedHypothesis

CorrectionMethod = Literal["holm", "benjamini_hochberg"]


def _validated_p_values(p_values: Sequence[float]) -> list[float]:
    if not p_values:
        raise ValueError("p_values must be non-empty")
    values = [float(value) for value in p_values]
    for index, value in enumerate(values):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"p_values[{index}] must be finite and in [0, 1]")
    return values


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Return Holm step-down family-wise adjusted p-values in original order."""
    values = _validated_p_values(p_values)
    m = len(values)
    order = sorted(range(m), key=values.__getitem__)
    adjusted_sorted: list[float] = []
    running = 0.0
    for rank, index in enumerate(order):
        candidate = (m - rank) * values[index]
        running = max(running, candidate)
        adjusted_sorted.append(min(1.0, running))
    adjusted = [0.0] * m
    for index, value in zip(order, adjusted_sorted, strict=True):
        adjusted[index] = value
    return adjusted


def benjamini_hochberg_adjust(p_values: Sequence[float]) -> list[float]:
    """Return Benjamini-Hochberg FDR adjusted p-values in original order."""
    values = _validated_p_values(p_values)
    m = len(values)
    order = sorted(range(m), key=values.__getitem__)
    adjusted_sorted = [0.0] * m
    running = 1.0
    for reverse_rank in range(m - 1, -1, -1):
        original_index = order[reverse_rank]
        rank = reverse_rank + 1
        candidate = values[original_index] * m / rank
        running = min(running, candidate)
        adjusted_sorted[reverse_rank] = min(1.0, running)
    adjusted = [0.0] * m
    for sorted_index, original_index in enumerate(order):
        adjusted[original_index] = adjusted_sorted[sorted_index]
    return adjusted


def adjust_hypotheses(
    hypothesis_ids: Sequence[str],
    p_values: Sequence[float],
    *,
    method: CorrectionMethod,
    alpha: float = 0.05,
) -> list[AdjustedHypothesis]:
    """Build immutable hypothesis records after one declared correction family."""
    if len(hypothesis_ids) != len(p_values):
        raise ValueError("hypothesis_ids and p_values must have equal length")
    if not hypothesis_ids:
        raise ValueError("hypothesis_ids must be non-empty")
    if len(set(hypothesis_ids)) != len(hypothesis_ids):
        raise ValueError("hypothesis_ids must be unique")
    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be finite and in (0, 1)")

    values = _validated_p_values(p_values)
    if method == "holm":
        adjusted = holm_adjust(values)
    elif method == "benjamini_hochberg":
        adjusted = benjamini_hochberg_adjust(values)
    else:
        raise ValueError(f"unsupported correction method: {method}")

    return [
        AdjustedHypothesis(
            hypothesis_id=hypothesis_id,
            method=method,
            alpha=alpha,
            raw_p_value=raw,
            adjusted_p_value=corrected,
            rejected=corrected <= alpha,
        )
        for hypothesis_id, raw, corrected in zip(
            hypothesis_ids,
            values,
            adjusted,
            strict=True,
        )
    ]
