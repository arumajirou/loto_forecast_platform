from __future__ import annotations

from typing import Any

import numpy as np


def detailed_draw_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape or actual.ndim != 2 or actual.shape[1] != 7:
        raise ValueError("actual and predicted must have shape (n_draws, 7)")
    errors = np.abs(actual - predicted)
    within = errors <= 1
    hits = np.array([len(set(map(int, a)) & set(map(int, p))) for a, p in zip(actual, predicted)])
    position_rates = within.mean(axis=0)
    result: dict[str, Any] = {
        "draws": int(len(actual)),
        "mean_hits_at_7": float(hits.mean()),
        "hits_std": float(hits.std(ddof=1)) if len(hits) > 1 else 0.0,
        "hits_distribution": {str(k): int((hits == k).sum()) for k in range(8)},
        "position_mae": float(errors.mean()),
        "position_mse": float(np.square(actual - predicted).mean()),
        "position_rmse": float(np.sqrt(np.square(actual - predicted).mean())),
        "median_absolute_error": float(np.median(errors)),
        "mean_within_1": float(within.mean()),
        "element_hit_within_1": float(within.mean()),
        "all_positions_within_1": float(within.all(axis=1).mean()),
        "row_hit_within_1": float(within.all(axis=1).mean()),
        "worst_position_within_1": float(position_rates.min()),
        "exact_position_rate": float((errors == 0).mean()),
        "exact_row_rate": float((errors == 0).all(axis=1).mean()),
        "within_2_rate": float((errors <= 2).mean()),
        "positions_within_1_mean": float(within.sum(axis=1).mean()),
        "positions_within_1_distribution": {
            str(k): int((within.sum(axis=1) == k).sum()) for k in range(8)
        },
    }
    for index, rate in enumerate(position_rates, start=1):
        result[f"position_{index}_within_1"] = float(rate)
        result[f"position_{index}_mae"] = float(errors[:, index - 1].mean())
        result[f"position_{index}_mse"] = float(np.square(actual[:, index - 1] - predicted[:, index - 1]).mean())
    return result


def candidate_ranking_metrics(targets: np.ndarray, probabilities: np.ndarray, k: int = 7) -> dict[str, float]:
    targets = np.asarray(targets, dtype=float)
    probabilities = np.asarray(probabilities, dtype=float)
    if targets.shape != probabilities.shape or targets.ndim != 2:
        raise ValueError("targets and probabilities must be aligned 2-D arrays")
    k = min(k, targets.shape[1])
    precisions: list[float] = []
    recalls: list[float] = []
    ndcgs: list[float] = []
    for truth, score in zip(targets, probabilities):
        order = np.argsort(-score, kind="stable")[:k]
        rel = truth[order]
        hits = float(rel.sum())
        positives = max(float(truth.sum()), 1.0)
        precisions.append(hits / k)
        recalls.append(hits / positives)
        discounts = 1.0 / np.log2(np.arange(2, k + 2))
        dcg = float((rel * discounts).sum())
        ideal = np.sort(truth)[::-1][:k]
        idcg = float((ideal * discounts).sum())
        ndcgs.append(dcg / idcg if idcg else 0.0)
    return {
        f"precision_at_{k}": float(np.mean(precisions)),
        f"recall_at_{k}": float(np.mean(recalls)),
        f"ndcg_at_{k}": float(np.mean(ndcgs)),
    }


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 10) -> float:
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_prob = np.asarray(y_prob, dtype=float).ravel()
    if y_true.shape != y_prob.shape:
        raise ValueError("shape mismatch")
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    value = 0.0
    for low, high in zip(boundaries[:-1], boundaries[1:]):
        mask = (y_prob >= low) & (y_prob < high if high < 1.0 else y_prob <= high)
        if mask.any():
            value += mask.mean() * abs(y_true[mask].mean() - y_prob[mask].mean())
    return float(value)


def composite_score(metrics: dict[str, float], weights: dict[str, float]) -> float:
    return float(sum(weight * float(metrics[key]) for key, weight in weights.items() if key in metrics))
