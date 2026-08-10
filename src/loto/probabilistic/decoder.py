from __future__ import annotations

from enum import StrEnum
from functools import cache

import numpy as np

from loto.game.geometry import GameGeometry


class DecodeObjective(StrEnum):
    """Explicit objective used by constrained select-game decoding."""

    MAP = "map"
    WITHIN_TAU = "within_tau"


def _validate_positional_probabilities(
    probabilities: np.ndarray, geometry: GameGeometry
) -> np.ndarray:
    probs = np.asarray(probabilities, dtype=float)
    expected = (geometry.positions, geometry.universe_size)
    if probs.shape != expected:
        raise ValueError(f"expected {expected}, got {probs.shape}")
    if not np.isfinite(probs).all():
        raise ValueError("probabilities must be finite")
    if np.any(probs < 0):
        raise ValueError("probabilities must be non-negative")
    totals = probs.sum(axis=1)
    if np.any(totals <= 0):
        raise ValueError("each positional probability row must have positive mass")
    return probs / totals[:, None]


def build_within_tau_utility(
    probabilities: np.ndarray,
    geometry: GameGeometry,
    *,
    tau: int = 1,
) -> np.ndarray:
    """Expected per-position Hit@±tau utility for every candidate value.

    ``probabilities`` contains positional marginals with shape
    ``(geometry.positions, geometry.universe_size)``. Rows are normalised independently so
    callers may provide probability masses that are proportional rather than exactly summing to
    one, but negative/non-finite/zero-mass rows are rejected.
    """
    if tau < 0:
        raise ValueError("tau must be >= 0")
    probs = _validate_positional_probabilities(probabilities, geometry)
    kernel = np.ones(2 * tau + 1, dtype=float)
    return np.vstack([np.convolve(row, kernel, mode="same") for row in probs])


def _decode_increasing_additive(scores: np.ndarray, geometry: GameGeometry) -> list[int]:
    """Maximise an additive score under the strict increasing select-game constraint."""
    matrix = np.asarray(scores, dtype=float)
    expected = (geometry.positions, geometry.universe_size)
    if matrix.shape != expected:
        raise ValueError(f"expected {expected}, got {matrix.shape}")
    if not np.isfinite(matrix).all():
        raise ValueError("scores must be finite")

    @cache
    def solve(position: int, previous: int) -> tuple[float, tuple[int, ...]]:
        if position == geometry.positions:
            return 0.0, ()
        remaining = geometry.positions - position - 1
        best_score = -float("inf")
        best_indexes: tuple[int, ...] = ()
        max_index = geometry.universe_size - remaining
        for index in range(previous + 1, max_index):
            tail_score, tail = solve(position + 1, index)
            score = float(matrix[position, index]) + tail_score
            candidate = (index,) + tail
            if score > best_score or (
                np.isclose(score, best_score) and (not best_indexes or candidate < best_indexes)
            ):
                best_score = score
                best_indexes = candidate
        return best_score, best_indexes

    _, indexes = solve(0, -1)
    values = [index + geometry.value_min for index in indexes]
    geometry.validate_outcome(values)
    return values


def decode_select_distribution(
    probabilities: np.ndarray,
    geometry: GameGeometry,
    *,
    objective: DecodeObjective | str = DecodeObjective.MAP,
    tau: int = 1,
) -> list[int]:
    """Decode positional marginals under an explicit scientific objective.

    ``MAP`` preserves the existing maximum-log-probability constrained decode.
    ``WITHIN_TAU`` maximises expected positional Hit@±``tau`` while keeping the output legal.
    """
    if geometry.family != "select":
        raise ValueError("decode_select_distribution requires a select-family geometry")
    resolved = DecodeObjective(objective)
    probs = _validate_positional_probabilities(probabilities, geometry)
    if resolved is DecodeObjective.MAP:
        scores = np.log(np.maximum(probs, 1e-15))
    else:
        scores = build_within_tau_utility(probs, geometry, tau=tau)
    return _decode_increasing_additive(scores, geometry)


def decode_select_positions(probabilities: np.ndarray, geometry: GameGeometry) -> list[int]:
    """Maximum-score strictly increasing MAP decode for select-game positional marginals.

    This compatibility API intentionally keeps its historical MAP semantics. Use
    :func:`decode_select_distribution` with ``objective=\"within_tau\"`` for Hit@±tau decoding.
    """
    probs = np.asarray(probabilities, dtype=float)
    if probs.shape != (geometry.positions, geometry.universe_size):
        # Candidate inclusion distribution: select the top-k candidates. This compatibility path
        # is intentionally left unchanged and is not a positional Hit@±tau decoder.
        if probs.ndim == 2 and probs.shape[0] == 1 and probs.shape[1] == geometry.universe_size:
            chosen = np.argpartition(probs[0], -geometry.positions)[-geometry.positions :]
            values = sorted((chosen + geometry.value_min).tolist())
            geometry.validate_outcome(values)
            return values
        raise ValueError(
            f"expected {(geometry.positions, geometry.universe_size)}, got {probs.shape}"
        )
    return decode_select_distribution(probs, geometry, objective=DecodeObjective.MAP)


def decode(
    probabilities: np.ndarray, geometry: GameGeometry, point_values: np.ndarray
) -> list[int]:
    if geometry.family == "digits":
        values = [int(x) for x in point_values.tolist()]
        geometry.validate_outcome(values)
        return values
    return decode_select_positions(probabilities, geometry)
