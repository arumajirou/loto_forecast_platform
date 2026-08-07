from __future__ import annotations

import numpy as np

from loto.adapters.timesfm25.contracts import GameGeometry


def rounded(values: list[float]) -> list[int]:
    return [int(np.rint(value)) for value in values]


def clipped_rounded(values: list[float], geometry: GameGeometry) -> list[int]:
    return [
        int(np.clip(np.rint(value), geometry.candidate_min, geometry.candidate_max))
        for value in values
    ]


def constrained_integer_projection(values: list[float], geometry: GameGeometry) -> list[int]:
    if len(values) != geometry.position_count:
        raise ValueError("values length must equal geometry.position_count")
    if not geometry.strictly_increasing:
        return clipped_rounded(values, geometry)

    candidates = list(range(geometry.candidate_min, geometry.candidate_max + 1))
    positions = len(values)
    infinity = float("inf")
    costs = [[infinity] * len(candidates) for _ in range(positions)]
    parent = [[-1] * len(candidates) for _ in range(positions)]

    for candidate_index, candidate in enumerate(candidates):
        costs[0][candidate_index] = (candidate - values[0]) ** 2

    for position in range(1, positions):
        best_cost = infinity
        best_index = -1
        for candidate_index, candidate in enumerate(candidates):
            previous_index = candidate_index - 1
            if previous_index >= 0 and costs[position - 1][previous_index] < best_cost:
                best_cost = costs[position - 1][previous_index]
                best_index = previous_index
            if best_index >= 0:
                costs[position][candidate_index] = best_cost + (candidate - values[position]) ** 2
                parent[position][candidate_index] = best_index

    last_index = min(range(len(candidates)), key=lambda index: costs[-1][index])
    if not np.isfinite(costs[-1][last_index]):
        raise ValueError("no feasible constrained integer projection")
    output = [0] * positions
    for position in range(positions - 1, -1, -1):
        output[position] = candidates[last_index]
        last_index = parent[position][last_index]
    return output
