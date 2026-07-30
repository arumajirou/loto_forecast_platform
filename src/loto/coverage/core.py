from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class CoverageConfig:
    target_coverage: float = 0.90
    tolerance: int = 1
    max_candidates: int = 5000
    pool_size: int = 20000
    per_position_top: int = 7
    beam_width: int = 20000
    diversity_penalty: float = 0.05
    calibration_margin: float = 0.02

    def __post_init__(self) -> None:
        if not 0 < self.target_coverage <= 1:
            raise ValueError("target_coverage must be in (0, 1]")
        if self.tolerance < 0:
            raise ValueError("tolerance must be non-negative")
        if min(self.max_candidates, self.pool_size, self.per_position_top, self.beam_width) <= 0:
            raise ValueError("candidate limits must be positive")


@dataclass
class PredictionSet:
    candidates: list[tuple[int, ...]]
    target_coverage: float
    calibration_coverage: float
    tolerance: int
    conformal_radius: int
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "candidates": [list(row) for row in self.candidates],
            "candidate_count": len(self.candidates),
            "target_coverage": self.target_coverage,
            "calibration_coverage": self.calibration_coverage,
            "tolerance": self.tolerance,
            "conformal_radius": self.conformal_radius,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class CoverageEvaluation:
    draws: int
    candidate_count: int
    row_within_tolerance: float
    element_within_tolerance: float
    mean_best_mae: float
    median_best_mae: float
    exact_row_rate: float
    positions_within_tolerance_mean: float

    def to_dict(self) -> dict:
        return asdict(self)


def legal_loto7(row: Sequence[int]) -> tuple[int, ...] | None:
    values = tuple(int(v) for v in row)
    if len(values) != 7 or any(v < 1 or v > 37 for v in values):
        return None
    if tuple(sorted(values)) != values or len(set(values)) != 7:
        return None
    return values



def project_to_legal(row: Sequence[int]) -> tuple[int, ...]:
    values = np.clip(np.rint(np.asarray(row, dtype=float)), 1, 37).astype(int)
    values.sort()
    for i in range(1, 7):
        values[i] = max(values[i], values[i - 1] + 1)
    if values[-1] > 37:
        shift = values[-1] - 37
        values -= shift
        for i in range(5, -1, -1):
            values[i] = min(values[i], values[i + 1] - 1)
    if values[0] < 1:
        values = np.arange(1, 8)
    return tuple(int(v) for v in values)


def _coverage_mask(actual: np.ndarray, candidate: Sequence[int], tolerance: int) -> np.ndarray:
    cand = np.asarray(candidate, dtype=int).reshape(1, 7)
    return np.max(np.abs(actual - cand), axis=1) <= tolerance


def evaluate_candidates(actual: Sequence[Sequence[int]], candidates: Sequence[Sequence[int]], tolerance: int = 1) -> CoverageEvaluation:
    actual_arr = np.asarray(actual, dtype=int)
    candidate_arr = np.asarray(candidates, dtype=int)
    if actual_arr.ndim != 2 or actual_arr.shape[1] != 7:
        raise ValueError("actual must have shape (n, 7)")
    if candidate_arr.ndim != 2 or candidate_arr.shape[1] != 7 or len(candidate_arr) == 0:
        raise ValueError("candidates must have shape (k, 7) and be non-empty")
    errors = np.abs(actual_arr[:, None, :] - candidate_arr[None, :, :])
    row_ok = np.max(errors, axis=2) <= tolerance
    best_index = np.argmin(np.mean(errors, axis=2), axis=1)
    best_errors = errors[np.arange(len(actual_arr)), best_index]
    return CoverageEvaluation(
        draws=len(actual_arr),
        candidate_count=len(candidate_arr),
        row_within_tolerance=float(np.mean(np.any(row_ok, axis=1))),
        element_within_tolerance=float(np.mean(best_errors <= tolerance)),
        mean_best_mae=float(np.mean(best_errors)),
        median_best_mae=float(np.median(np.mean(best_errors, axis=1))),
        exact_row_rate=float(np.mean(np.any(np.max(errors, axis=2) == 0, axis=1))),
        positions_within_tolerance_mean=float(np.mean(np.sum(best_errors <= tolerance, axis=1))),
    )


def simultaneous_conformal_radius(actual: Sequence[Sequence[int]], predicted: Sequence[Sequence[int]], coverage: float = 0.90) -> int:
    a = np.asarray(actual, dtype=int)
    p = np.asarray(predicted, dtype=int)
    if a.shape != p.shape or a.ndim != 2 or a.shape[1] != 7:
        raise ValueError("actual and predicted must have matching shape (n, 7)")
    scores = np.max(np.abs(a - p), axis=1)
    n = len(scores)
    if n == 0:
        raise ValueError("calibration data is empty")
    rank = min(n, int(np.ceil((n + 1) * coverage)))
    return int(np.partition(scores, rank - 1)[rank - 1])


def position_probabilities(history: Sequence[Sequence[int]], centers: Sequence[float], scales: Sequence[float] | None = None) -> np.ndarray:
    values = np.asarray(history, dtype=float)
    centers_arr = np.asarray(centers, dtype=float)
    if values.ndim != 2 or values.shape[1] != 7:
        raise ValueError("history must have shape (n, 7)")
    if scales is None:
        diffs = np.diff(values, axis=0)
        mad = np.median(np.abs(diffs - np.median(diffs, axis=0)), axis=0) if len(diffs) else np.ones(7)
        scales_arr = np.clip(1.4826 * mad, 0.75, 6.0)
    else:
        scales_arr = np.clip(np.asarray(scales, dtype=float), 0.5, 10.0)
    candidates = np.arange(1, 38, dtype=float)
    matrix = []
    for center, scale in zip(centers_arr, scales_arr, strict=True):
        weights = np.exp(-0.5 * ((candidates - center) / scale) ** 2)
        weights /= max(float(weights.sum()), 1e-12)
        matrix.append(weights)
    return np.asarray(matrix)


def generate_candidate_pool(
    probability_matrix: np.ndarray,
    *,
    per_position_top: int = 7,
    beam_width: int = 20000,
    pool_size: int = 20000,
) -> list[tuple[int, ...]]:
    probs = np.asarray(probability_matrix, dtype=float)
    if probs.shape != (7, 37):
        raise ValueError("probability_matrix must have shape (7, 37)")
    choices: list[list[tuple[int, float]]] = []
    for position in range(7):
        order = np.argsort(probs[position])[::-1][:per_position_top]
        choices.append([(int(idx + 1), float(np.log(max(probs[position, idx], 1e-15)))) for idx in order])

    beam: list[tuple[tuple[int, ...], float]] = [(tuple(), 0.0)]
    for pos_choices in choices:
        expanded: list[tuple[tuple[int, ...], float]] = []
        for prefix, score in beam:
            lower = prefix[-1] + 1 if prefix else 1
            for value, logp in pos_choices:
                if value < lower:
                    continue
                expanded.append((prefix + (value,), score + logp))
        expanded.sort(key=lambda item: item[1], reverse=True)
        beam = expanded[:beam_width]
        if not beam:
            break
    legal = [(row, score) for row, score in beam if legal_loto7(row) is not None]
    legal.sort(key=lambda item: item[1], reverse=True)
    return [row for row, _ in legal[:pool_size]]


def augment_with_residual_offsets(
    centers: Sequence[int], residuals: Sequence[Sequence[int]], *, radius: int = 1, limit: int = 20000
) -> list[tuple[int, ...]]:
    center = np.asarray(centers, dtype=int)
    residual_arr = np.asarray(residuals, dtype=int)
    offsets: set[tuple[int, ...]] = {tuple(np.clip(row, -8, 8).tolist()) for row in residual_arr}
    local = list(product(range(-radius, radius + 1), repeat=7))
    offsets.update(tuple(int(x) for x in row) for row in local)
    rows: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for offset in offsets:
        raw = center + np.asarray(offset, dtype=int)
        row = project_to_legal(raw)
        if row not in seen:
            seen.add(row)
            rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def greedy_coverage_select(
    actual: Sequence[Sequence[int]],
    pool: Sequence[Sequence[int]],
    *,
    target_coverage: float = 0.90,
    tolerance: int = 1,
    max_candidates: int = 5000,
    diversity_penalty: float = 0.05,
) -> tuple[list[tuple[int, ...]], list[dict]]:
    actual_arr = np.asarray(actual, dtype=int)
    legal_pool = [legal_loto7(row) for row in pool]
    legal_pool = list(dict.fromkeys(row for row in legal_pool if row is not None))
    if not legal_pool:
        raise ValueError("candidate pool is empty")
    masks = np.vstack([_coverage_mask(actual_arr, row, tolerance) for row in legal_pool])
    uncovered = np.ones(len(actual_arr), dtype=bool)
    selected: list[tuple[int, ...]] = []
    trace: list[dict] = []
    remaining = np.ones(len(legal_pool), dtype=bool)
    target_count = int(np.ceil(target_coverage * len(actual_arr)))
    while int((~uncovered).sum()) < target_count and len(selected) < max_candidates:
        gains = np.sum(masks[:, uncovered], axis=1).astype(float)
        gains[~remaining] = -np.inf
        if selected and diversity_penalty > 0:
            selected_arr = np.asarray(selected, dtype=float)
            pool_arr = np.asarray(legal_pool, dtype=float)
            distances = np.min(np.mean(np.abs(pool_arr[:, None, :] - selected_arr[None, :, :]), axis=2), axis=1)
            gains += diversity_penalty * distances
        index = int(np.argmax(gains))
        raw_gain = int(np.sum(masks[index] & uncovered))
        if raw_gain <= 0:
            if not selected:
                selected.append(legal_pool[index])
                trace.append({"step": 1, "candidate": list(legal_pool[index]), "newly_covered": 0, "coverage": 0.0})
            break
        remaining[index] = False
        selected.append(legal_pool[index])
        uncovered &= ~masks[index]
        coverage = float(np.mean(~uncovered))
        trace.append({"step": len(selected), "candidate": list(legal_pool[index]), "newly_covered": raw_gain, "coverage": coverage})
    return selected, trace
