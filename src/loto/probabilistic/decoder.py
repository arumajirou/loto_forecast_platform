from __future__ import annotations

from functools import cache

import numpy as np

from loto.game.geometry import GameGeometry


def decode_select_positions(probabilities: np.ndarray, geometry: GameGeometry) -> list[int]:
    """Maximum-score strictly increasing decode for select-game positional marginals."""
    probs = np.asarray(probabilities, dtype=float)
    if probs.shape != (geometry.positions, geometry.universe_size):
        # Candidate inclusion distribution: select the top-k candidates.
        if probs.shape[0] == 1 and probs.shape[1] == geometry.universe_size:
            chosen = np.argpartition(probs[0], -geometry.positions)[-geometry.positions :]
            return sorted((chosen + geometry.value_min).tolist())
        raise ValueError(
            f"expected {(geometry.positions, geometry.universe_size)}, got {probs.shape}"
        )
    logp = np.log(np.maximum(probs, 1e-15))

    @cache
    def solve(position: int, previous: int) -> tuple[float, tuple[int, ...]]:
        if position == geometry.positions:
            return 0.0, ()
        remaining = geometry.positions - position - 1
        best_score = -float("inf")
        best_values: tuple[int, ...] = ()
        max_index = geometry.universe_size - remaining
        for index in range(previous + 1, max_index):
            tail_score, tail = solve(position + 1, index)
            score = float(logp[position, index]) + tail_score
            if score > best_score:
                best_score = score
                best_values = (index,) + tail
        return best_score, best_values

    _, indexes = solve(0, -1)
    values = [index + geometry.value_min for index in indexes]
    geometry.validate_outcome(values)
    return values


def decode(
    probabilities: np.ndarray, geometry: GameGeometry, point_values: np.ndarray
) -> list[int]:
    if geometry.family == "digits":
        values = [int(x) for x in point_values.tolist()]
        geometry.validate_outcome(values)
        return values
    return decode_select_positions(probabilities, geometry)
