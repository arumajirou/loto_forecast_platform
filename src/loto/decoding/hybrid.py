"""Legacy Loto7 additive constrained decoding with optional combination reranking.

New geometry-general probability decoding lives in :mod:`loto.probabilistic.decoder`. This
function keeps the historical :class:`loto.contracts.DecodedCombination` contract, but derives
all Loto7 dimensions from the canonical game geometry instead of duplicating numeric literals.
"""

from __future__ import annotations

import numpy as np

from loto.contracts import DecodedCombination
from loto.game.geometry import geometry_for


def decode_hybrid(
    candidate_scores: np.ndarray,
    position_scores: np.ndarray,
    *,
    top_k: int = 20,
    candidate_weight: float = 1.0,
    position_weight: float = 1.0,
    cooccurrence: np.ndarray | None = None,
    cooccurrence_weight: float = 0.0,
) -> list[DecodedCombination]:
    geometry = geometry_for("loto7")
    candidate_scores = np.asarray(candidate_scores, dtype=float)
    position_scores = np.asarray(position_scores, dtype=float)
    candidate_shape = (geometry.universe_size,)
    position_shape = (geometry.positions, geometry.universe_size)
    if candidate_scores.shape != candidate_shape or position_scores.shape != position_shape:
        raise ValueError(
            f"expected candidate_scores={candidate_shape}, position_scores={position_shape}"
        )
    if cooccurrence is not None and np.asarray(cooccurrence).shape != (
        geometry.universe_size,
        geometry.universe_size,
    ):
        raise ValueError("cooccurrence matrix must match the canonical Loto7 universe")

    # states[last_number] = top paths ending in last_number for current position.
    states: dict[int, list[tuple[float, tuple[int, ...]]]] = {}
    for number in geometry.values:
        if geometry.value_max - number < geometry.positions - 1:
            continue
        index = number - geometry.value_min
        score = (
            candidate_weight * candidate_scores[index] + position_weight * position_scores[0, index]
        )
        states[number] = [(float(score), (number,))]
    for position in range(1, geometry.positions):
        new_states: dict[int, list[tuple[float, tuple[int, ...]]]] = {}
        minimum_number = geometry.value_min + position
        for number in range(minimum_number, geometry.value_max + 1):
            if geometry.value_max - number < geometry.positions - 1 - position:
                continue
            candidates: list[tuple[float, tuple[int, ...]]] = []
            index = number - geometry.value_min
            add = (
                candidate_weight * candidate_scores[index]
                + position_weight * position_scores[position, index]
            )
            for previous, paths in states.items():
                if previous >= number:
                    continue
                candidates.extend((score + float(add), path + (number,)) for score, path in paths)
            if candidates:
                candidates.sort(key=lambda item: (-item[0], item[1]))
                new_states[number] = candidates[:top_k]
        states = new_states
    all_paths = [item for paths in states.values() for item in paths]
    rescored: list[tuple[float, tuple[int, ...]]] = []
    for score, path in all_paths:
        if cooccurrence is not None and cooccurrence_weight:
            pair_score = sum(
                float(
                    cooccurrence[
                        first - geometry.value_min,
                        second - geometry.value_min,
                    ]
                )
                for index, first in enumerate(path)
                for second in path[index + 1 :]
            )
            score += cooccurrence_weight * pair_score
        rescored.append((score, path))
    rescored.sort(key=lambda item: (-item[0], item[1]))
    return [
        DecodedCombination(numbers=list(path), score=float(score))
        for score, path in rescored[:top_k]
    ]
