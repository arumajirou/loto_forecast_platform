from __future__ import annotations

from typing import Iterable

import numpy as np


def score_combination(predicted: Iterable[int], actual: Iterable[int]) -> dict[str, float]:
    p = np.asarray(sorted(predicted), dtype=float)
    a = np.asarray(sorted(actual), dtype=float)
    if len(p) != 7 or len(a) != 7:
        raise ValueError("predicted and actual must each contain seven numbers")
    hits = len(set(map(int, p)) & set(map(int, a)))
    errors = np.abs(p - a)
    return {
        "hits_at_7": float(hits),
        "position_mae": float(errors.mean()),
        "position_mse": float((errors ** 2).mean()),
        "within_1_rate": float((errors <= 1).mean()),
    }
