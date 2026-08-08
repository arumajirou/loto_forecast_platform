from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ensemble_conformal_contract import (
    CertificationError,
    TemporalPartition,
    canonical_sha256,
)


class ForecastPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_id: str = Field(min_length=1)
    seed: int
    fold_id: int = Field(ge=0)
    origin: int = Field(ge=0)
    target_index: int = Field(ge=0)
    position: str = Field(min_length=1)
    actual: float
    predicted: float

    @model_validator(mode="after")
    def validate_point(self) -> ForecastPoint:
        values = np.asarray([self.actual, self.predicted], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("forecast point contains NaN or Inf")
        if self.target_index < self.origin:
            raise ValueError("target_index must not precede origin")
        return self


class StackingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    training_records: tuple[ForecastPoint, ...]
    evaluation_records: tuple[ForecastPoint, ...]
    observed_base_model_ids: tuple[str, ...]
    observed_seeds: tuple[int, ...]
    observed_fold_ids: tuple[int, ...]


def certify_naive_average(
    base_predictions: Mapping[str, np.ndarray],
    ensemble_prediction: np.ndarray,
    *,
    base_model_ids: Sequence[str],
    atol: float = 1e-12,
) -> dict[str, Any]:
    if tuple(sorted(base_predictions)) != tuple(sorted(base_model_ids)):
        raise CertificationError("base prediction identities do not match the ensemble plan")
    arrays = [np.asarray(base_predictions[model_id], dtype=float) for model_id in base_model_ids]
    if not arrays:
        raise CertificationError("no base predictions supplied")
    shapes = {array.shape for array in arrays}
    if len(shapes) != 1 or any(array.ndim != 2 for array in arrays):
        raise CertificationError("base prediction shapes must match position x horizon")
    if any(not np.isfinite(array).all() for array in arrays):
        raise CertificationError("base predictions contain NaN or Inf")
    observed = np.asarray(ensemble_prediction, dtype=float)
    if observed.shape != arrays[0].shape or not np.isfinite(observed).all():
        raise CertificationError("ensemble prediction shape or finite-value check failed")
    expected = np.mean(np.stack(arrays, axis=0), axis=0)
    if not np.allclose(observed, expected, atol=atol, rtol=0.0):
        raise CertificationError("naive ensemble prediction differs from arithmetic mean")
    return {
        "base_model_ids": tuple(base_model_ids),
        "shape": tuple(int(value) for value in observed.shape),
        "max_abs_delta": float(np.max(np.abs(observed - expected))),
        "prediction_sha256": canonical_sha256(observed.tolist()),
    }


def certify_stacking_evidence(
    evidence: StackingEvidence,
    *,
    expected_base_model_ids: Sequence[str],
    expected_seeds: Sequence[int],
    expected_fold_ids: Sequence[int],
    partition: TemporalPartition,
) -> dict[str, Any]:
    if tuple(evidence.observed_base_model_ids) != tuple(expected_base_model_ids):
        raise CertificationError("stacking base model order or identity mismatch")
    if tuple(evidence.observed_seeds) != tuple(expected_seeds):
        raise CertificationError("stacking seed coverage mismatch")
    if tuple(evidence.observed_fold_ids) != tuple(expected_fold_ids):
        raise CertificationError("stacking fold coverage mismatch")
    if not evidence.training_records or not evidence.evaluation_records:
        raise CertificationError("stacking requires training and evaluation records")
    training_keys = {
        (item.seed, item.fold_id, item.target_index, item.position)
        for item in evidence.training_records
    }
    evaluation_keys = {
        (item.seed, item.fold_id, item.target_index, item.position)
        for item in evidence.evaluation_records
    }
    if any(
        not partition.train_start <= item.origin < partition.calibration_end
        or item.target_index >= partition.evaluation_start
        for item in evidence.training_records
    ):
        raise CertificationError("stacking record uses evaluation-period information")
    overlap = training_keys & evaluation_keys
    if overlap:
        raise CertificationError("stacking training and evaluation keys overlap")
    if any(
        item.origin < partition.evaluation_start or item.target_index >= partition.evaluation_end
        for item in evidence.evaluation_records
    ):
        raise CertificationError("evaluation records fall outside the evaluation partition")
    grouped: dict[tuple[int, int, int, str], set[str]] = defaultdict(set)
    for item in evidence.training_records:
        key = (item.seed, item.fold_id, item.target_index, item.position)
        grouped[key].add(item.model_id)
    required = set(expected_base_model_ids)
    incomplete = [key for key, model_ids in grouped.items() if model_ids != required]
    if incomplete:
        raise CertificationError("stacking rows do not contain every base model")
    return {
        "training_record_count": len(evidence.training_records),
        "evaluation_record_count": len(evidence.evaluation_records),
        "training_keys_sha256": canonical_sha256(sorted(training_keys)),
        "evaluation_keys_sha256": canonical_sha256(sorted(evaluation_keys)),
    }
