from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

LOWER_IS_BETTER = {"position_mae", "position_mse", "brier", "log_loss", "mae", "mse"}
HIGHER_IS_BETTER = {"element_within_1", "row_within_1", "mean_hits_at_7", "brier_skill_score", "accuracy"}


@dataclass(frozen=True)
class Comparison:
    name: str
    reference_condition: str
    comparison_condition: str


def contribution(reference: np.ndarray, comparison: np.ndarray, metric: str) -> np.ndarray:
    if metric in LOWER_IS_BETTER:
        return comparison - reference
    if metric in HIGHER_IS_BETTER:
        return reference - comparison
    raise ValueError(f"unsupported metric: {metric}")


def _normal_sf(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def paired_pvalue(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size < 2:
        return 1.0
    std = float(finite.std(ddof=1))
    if std == 0:
        return 0.0 if float(finite.mean()) != 0 else 1.0
    z = abs(float(finite.mean())) / (std / math.sqrt(finite.size))
    return min(1.0, 2.0 * _normal_sf(z))


def adjust_pvalues(pvalues: list[float], method: str) -> list[float]:
    n = len(pvalues)
    order = np.argsort(pvalues)
    adjusted = np.ones(n, dtype=float)
    if method == "holm":
        running = 0.0
        for rank, index in enumerate(order):
            running = max(running, (n - rank) * pvalues[index])
            adjusted[index] = min(1.0, running)
    elif method in {"bh", "fdr_bh"}:
        running = 1.0
        for reverse_rank, index in enumerate(order[::-1], start=1):
            rank = n - reverse_rank + 1
            running = min(running, pvalues[index] * n / rank)
            adjusted[index] = min(1.0, running)
    else:
        raise ValueError(f"unknown correction method: {method}")
    return adjusted.tolist()


def cluster_bootstrap(values_by_fold: pd.Series, *, iterations: int = 5000, seed: int = 42) -> tuple[float, float, float]:
    values = values_by_fold.to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(values), size=(iterations, len(values)))
    estimates = values[indexes].mean(axis=1)
    return tuple(float(x) for x in np.quantile(estimates, [0.025, 0.5, 0.975]))


def paired_summary(
    frame: pd.DataFrame,
    *,
    comparison: Comparison,
    metric: str,
    group_columns: tuple[str, ...] = ("model_id", "feature_group"),
    bootstrap_iterations: int = 5000,
) -> pd.DataFrame:
    keys = ["model_id", "fold", "seed"]
    reference = frame[frame["condition"].eq(comparison.reference_condition)]
    candidate = frame[frame["condition"].eq(comparison.comparison_condition)]
    if reference.empty or candidate.empty:
        raise ValueError(f"missing comparison rows for {comparison.name}")
    merge_keys = keys + (["feature_group"] if "feature_group" in candidate.columns else [])
    paired = candidate.merge(reference, on=keys, suffixes=("_comparison", "_reference"), validate="many_to_one")
    records: list[dict[str, object]] = []
    actual_groups = [column for column in group_columns if column in paired.columns]
    for group_key, group in paired.groupby(actual_groups, dropna=False, sort=True):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        values = contribution(
            group[f"{metric}_reference"].to_numpy(float),
            group[f"{metric}_comparison"].to_numpy(float),
            metric,
        )
        detail = group[["fold", "seed"]].copy()
        detail["contribution"] = values
        fold_mean = detail.groupby("fold")["contribution"].mean()
        seed_mean = detail.groupby("seed")["contribution"].mean()
        low, median, high = cluster_bootstrap(fold_mean, iterations=bootstrap_iterations)
        ordered = fold_mean.sort_index().to_numpy(float)
        midpoint = max(1, len(ordered) // 2)
        record = dict(zip(actual_groups, group_key, strict=True))
        record.update(
            comparison=comparison.name,
            metric=metric,
            paired_rows=len(group),
            unique_folds=detail["fold"].nunique(),
            unique_seeds=detail["seed"].nunique(),
            absolute_contribution=float(values.mean()),
            cluster_ci95_low=low,
            cluster_ci95_median=median,
            cluster_ci95_high=high,
            positive_fold_rate=float((fold_mean > 0).mean()),
            all_seeds_positive=bool((seed_mean > 0).all()),
            front_half_contribution=float(ordered[:midpoint].mean()),
            back_half_contribution=float(ordered[midpoint:].mean()) if len(ordered[midpoint:]) else float(ordered[:midpoint].mean()),
            pvalue=paired_pvalue(fold_mean.to_numpy(float)),
        )
        records.append(record)
    result = pd.DataFrame(records)
    if not result.empty:
        result["pvalue_holm"] = adjust_pvalues(result["pvalue"].tolist(), "holm")
        result["pvalue_bh"] = adjust_pvalues(result["pvalue"].tolist(), "bh")
    return result
