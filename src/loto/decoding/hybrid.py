"""Exact additive constrained decoding with optional combination reranking."""

from __future__ import annotations

import numpy as np

from loto.contracts import DecodedCombination


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
    candidate_scores = np.asarray(candidate_scores, dtype=float)
    position_scores = np.asarray(position_scores, dtype=float)
    if candidate_scores.shape != (37,) or position_scores.shape != (7, 37):
        raise ValueError("expected candidate_scores=(37,), position_scores=(7,37)")
    # states[last_number] = top paths ending in last_number for current position.
    states: dict[int, list[tuple[float, tuple[int, ...]]]] = {}
    for n in range(1, 38):
        if 37 - n < 6:
            continue
        score = (
            candidate_weight * candidate_scores[n - 1] + position_weight * position_scores[0, n - 1]
        )
        states[n] = [(float(score), (n,))]
    for pos in range(1, 7):
        new_states: dict[int, list[tuple[float, tuple[int, ...]]]] = {}
        for n in range(pos + 1, 38):
            if 37 - n < 6 - pos:
                continue
            candidates: list[tuple[float, tuple[int, ...]]] = []
            add = (
                candidate_weight * candidate_scores[n - 1]
                + position_weight * position_scores[pos, n - 1]
            )
            for prev, paths in states.items():
                if prev >= n:
                    continue
                candidates.extend((score + float(add), path + (n,)) for score, path in paths)
            if candidates:
                candidates.sort(key=lambda x: (-x[0], x[1]))
                new_states[n] = candidates[:top_k]
        states = new_states
    all_paths = [item for paths in states.values() for item in paths]
    rescored: list[tuple[float, tuple[int, ...]]] = []
    for score, path in all_paths:
        if cooccurrence is not None and cooccurrence_weight:
            pair_score = sum(
                float(cooccurrence[a - 1, b - 1]) for i, a in enumerate(path) for b in path[i + 1 :]
            )
            score += cooccurrence_weight * pair_score
        rescored.append((score, path))
    rescored.sort(key=lambda x: (-x[0], x[1]))
    return [
        DecodedCombination(numbers=list(path), score=float(score))
        for score, path in rescored[:top_k]
    ]
