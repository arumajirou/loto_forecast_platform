from __future__ import annotations

import numpy as np

from loto.adapters.moirai2.contracts import GameGeometry


def rounded_variant(values: np.ndarray) -> np.ndarray:
    return np.rint(np.asarray(values, dtype=float)).astype(int)


def clipped_rounded_variant(values: np.ndarray, geometry: GameGeometry) -> np.ndarray:
    rounded = rounded_variant(values)
    return np.clip(rounded, geometry.candidate_min, geometry.candidate_max)


def constrained_integer_projection(values: np.ndarray, geometry: GameGeometry) -> np.ndarray:
    """Project one horizon row onto the finite game domain with deterministic tie-breaking."""
    raw = np.asarray(values, dtype=float)
    if raw.shape != (geometry.position_count,):
        raise ValueError("values must match geometry.position_count")
    domain = np.arange(geometry.candidate_min, geometry.candidate_max + 1, dtype=int)
    if not geometry.strictly_increasing:
        return clipped_rounded_variant(raw, geometry)
    costs = (domain[None, :] - raw[:, None]) ** 2
    positions = geometry.position_count
    infinity = float("inf")
    dynamic = np.full((positions, len(domain)), infinity)
    parents = np.full((positions, len(domain)), -1, dtype=int)
    dynamic[0] = costs[0]
    for position in range(1, positions):
        for current in range(position, len(domain)):
            previous_slice = dynamic[position - 1, :current]
            previous = int(np.argmin(previous_slice))
            dynamic[position, current] = previous_slice[previous] + costs[position, current]
            parents[position, current] = previous
    current = int(np.argmin(dynamic[-1]))
    result = [domain[current]]
    for position in range(positions - 1, 0, -1):
        current = int(parents[position, current])
        result.append(domain[current])
    return np.asarray(result[::-1], dtype=int)
