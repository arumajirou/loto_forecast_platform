"""Typed exploratory-hypothesis adapter over the canonical evaluation multiplicity layer.

The repository already owns Holm and Benjamini-Hochberg implementations in
``loto.evaluation.multiplicity``.  Exploratory trend/dependence analysis needs a different
result schema (hypothesis IDs and immutable records), not a second statistics implementation.
This module therefore validates the exploratory family and delegates all p-value adjustment
to that canonical layer so model-evaluation and scientific-analysis corrections cannot drift.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from loto.analysis.contracts import AdjustedHypothesis
from loto.evaluation.multiplicity import benjamini_hochberg as _canonical_bh
from loto.evaluation.multiplicity import holm as _canonical_holm

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
    """Return canonical Holm adjusted p-values in original order."""
    values = _validated_p_values(p_values)
    return list(_canonical_holm(values).adjusted_p)


def benjamini_hochberg_adjust(p_values: Sequence[float]) -> list[float]:
    """Return canonical Benjamini-Hochberg adjusted p-values in original order."""
    values = _validated_p_values(p_values)
    return list(_canonical_bh(values).adjusted_p)


def adjust_hypotheses(
    hypothesis_ids: Sequence[str],
    p_values: Sequence[float],
    *,
    method: CorrectionMethod,
    alpha: float = 0.05,
) -> list[AdjustedHypothesis]:
    """Build immutable hypothesis records using the canonical correction engine."""
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
        correction = _canonical_holm(values, alpha=alpha)
    elif method == "benjamini_hochberg":
        correction = _canonical_bh(values, alpha=alpha)
    else:
        raise ValueError(f"unsupported correction method: {method}")

    return [
        AdjustedHypothesis(
            hypothesis_id=hypothesis_id,
            method=method,
            alpha=alpha,
            raw_p_value=raw,
            adjusted_p_value=corrected,
            rejected=rejected,
        )
        for hypothesis_id, raw, corrected, rejected in zip(
            hypothesis_ids,
            correction.raw_p,
            correction.adjusted_p,
            correction.rejected,
            strict=True,
        )
    ]
