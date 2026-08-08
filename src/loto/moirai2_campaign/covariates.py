from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


class CovariateCompilationError(ValueError):
    pass


@dataclass(frozen=True)
class CovariateMatrixEvidence:
    names: tuple[str, ...]
    shape: tuple[int, int]
    sha256: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "names": list(self.names),
            "shape": list(self.shape),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class CovariateBundle:
    past_feat_dynamic_real: np.ndarray | None
    feat_dynamic_real: np.ndarray | None
    past: CovariateMatrixEvidence
    known_future: CovariateMatrixEvidence
    known_future_tail_sha256: str | None
    chronology_valid: bool = True
    availability_verified: bool = True
    actuals_used: bool = False

    @property
    def past_dim(self) -> int:
        return len(self.past.names)

    @property
    def known_future_dim(self) -> int:
        return len(self.known_future.names)

    def as_dict(self) -> dict[str, object]:
        return {
            "past": self.past.as_dict(),
            "known_future": self.known_future.as_dict(),
            "known_future_tail_sha256": self.known_future_tail_sha256,
            "chronology_valid": self.chronology_valid,
            "availability_verified": self.availability_verified,
            "actuals_used": self.actuals_used,
        }


def _matrix_sha256(names: tuple[str, ...], matrix: np.ndarray | None) -> str | None:
    if matrix is None:
        return None
    contiguous = np.ascontiguousarray(matrix, dtype=np.float32)
    header = json.dumps(
        {"names": names, "shape": contiguous.shape, "dtype": "float32"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(header)
    digest.update(b"\0")
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _calendar_expand(
    matrix: np.ndarray,
    timestamps: Sequence[datetime],
) -> np.ndarray:
    if matrix.shape[1] != len(timestamps):
        raise CovariateCompilationError("calendar timestamps must match covariate history")
    normalized = pd.DatetimeIndex(pd.to_datetime(list(timestamps), utc=True))
    if normalized.has_duplicates or not normalized.is_monotonic_increasing:
        raise CovariateCompilationError("calendar timestamps must be unique and increasing")
    complete = pd.date_range(normalized[0], normalized[-1], freq="D", tz="UTC")
    expanded = np.full((matrix.shape[0], len(complete)), np.nan, dtype=np.float32)
    locations = complete.get_indexer(normalized)
    if np.any(locations < 0):
        raise CovariateCompilationError("calendar timestamp could not be mapped")
    expanded[:, locations] = matrix
    return expanded


def _ordered_matrix(
    values: Mapping[str, Sequence[float | int]],
    *,
    start: int,
    stop: int,
) -> tuple[tuple[str, ...], np.ndarray | None]:
    names = tuple(sorted(values))
    if not names:
        return names, None
    rows = [np.asarray(values[name][start:stop], dtype=np.float32) for name in names]
    matrix = np.stack(rows, axis=0)
    if not np.isfinite(matrix).all():
        raise CovariateCompilationError("covariate values must be finite")
    return names, matrix


def compile_covariates(
    *,
    history_length: int,
    context_length: int,
    prediction_length: int,
    past_covariates: Mapping[str, Sequence[float | int]],
    future_covariates: Mapping[str, Sequence[float | int]],
    future_covariate_availability: Mapping[str, str],
    time_semantics: str,
    context_timestamps: Sequence[datetime | int],
    target_time_length: int,
) -> CovariateBundle:
    if history_length < context_length:
        raise CovariateCompilationError("history is shorter than context_length")
    if target_time_length < context_length:
        raise CovariateCompilationError("target time axis is shorter than context_length")
    if set(future_covariates) != set(future_covariate_availability):
        raise CovariateCompilationError("known-future availability evidence is incomplete")
    if any(value != "known_at_prediction_time" for value in future_covariate_availability.values()):
        raise CovariateCompilationError("future covariate is not known at prediction time")

    history_start = history_length - context_length
    past_names, past_matrix = _ordered_matrix(
        past_covariates,
        start=history_start,
        stop=history_length,
    )
    future_names, future_history = _ordered_matrix(
        future_covariates,
        start=history_start,
        stop=history_length,
    )
    _, future_tail = _ordered_matrix(
        future_covariates,
        start=history_length,
        stop=history_length + prediction_length,
    )

    if time_semantics == "calendar_time":
        calendar_timestamps = [value for value in context_timestamps if isinstance(value, datetime)]
        if len(calendar_timestamps) != len(context_timestamps):
            raise CovariateCompilationError("calendar_time requires datetime timestamps")
        if past_matrix is not None:
            past_matrix = _calendar_expand(past_matrix, calendar_timestamps)
        if future_history is not None:
            future_history = _calendar_expand(future_history, calendar_timestamps)
    elif time_semantics != "draw_sequence":
        raise CovariateCompilationError(f"unsupported time semantics: {time_semantics}")

    if past_matrix is not None and past_matrix.shape[1] != target_time_length:
        raise CovariateCompilationError("past covariates do not align with target time axis")
    if future_history is not None and future_history.shape[1] != target_time_length:
        raise CovariateCompilationError(
            "future covariate history does not align with target time axis"
        )

    feat_dynamic_real = None
    if future_history is not None:
        if future_tail is None or future_tail.shape != (
            len(future_names),
            prediction_length,
        ):
            raise CovariateCompilationError("known-future tail has the wrong shape")
        feat_dynamic_real = np.concatenate([future_history, future_tail], axis=1)

    past_evidence = CovariateMatrixEvidence(
        names=past_names,
        shape=(0, 0) if past_matrix is None else past_matrix.shape,
        sha256=_matrix_sha256(past_names, past_matrix),
    )
    future_evidence = CovariateMatrixEvidence(
        names=future_names,
        shape=(0, 0) if feat_dynamic_real is None else feat_dynamic_real.shape,
        sha256=_matrix_sha256(future_names, feat_dynamic_real),
    )
    tail_hash = _matrix_sha256(future_names, future_tail)
    return CovariateBundle(
        past_feat_dynamic_real=past_matrix,
        feat_dynamic_real=feat_dynamic_real,
        past=past_evidence,
        known_future=future_evidence,
        known_future_tail_sha256=tail_hash,
    )


def attach_covariates(
    dataset_entry: dict[str, object],
    bundle: CovariateBundle,
) -> dict[str, object]:
    result = dict(dataset_entry)
    if bundle.past_feat_dynamic_real is not None:
        result["past_feat_dynamic_real"] = bundle.past_feat_dynamic_real
    if bundle.feat_dynamic_real is not None:
        result["feat_dynamic_real"] = bundle.feat_dynamic_real
    return result
