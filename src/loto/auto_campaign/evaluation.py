from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .metrics import prediction_variants, score_draw_matrix


def _task_payload(path: Path) -> dict[str, Any]:
    return json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))


def collect_task_metrics(run_root: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in run_root.glob("tasks/**/metrics_by_variant.parquet"):
        frame = pd.read_parquet(path)
        payload = _task_payload(path)
        for key, value in payload["task"].items():
            frame[key] = value
        frame["task_manifest"] = str(path.parent / "manifest.json")
        rows.append(frame)
    if rows:
        return pd.concat(rows, ignore_index=True)

    legacy_rows: list[dict[str, Any]] = []
    for manifest_path in run_root.glob("tasks/**/manifest.json"):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        metrics = payload.get("metrics") or {}
        if metrics:
            legacy_rows.append(
                {
                    **payload["task"],
                    **metrics,
                    "task_manifest": str(manifest_path),
                }
            )
    return pd.DataFrame(legacy_rows)


def collect_position_metrics(run_root: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in run_root.glob("tasks/**/position_metrics.parquet"):
        frame = pd.read_parquet(path)
        payload = _task_payload(path)
        for key, value in payload["task"].items():
            frame[key] = value
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _combined_local_metrics(run_root: Path) -> pd.DataFrame:
    prediction_parts: list[pd.DataFrame] = []
    for path in run_root.glob("tasks/**/prediction_records.parquet"):
        payload = _task_payload(path)
        task = payload["task"]
        if task.get("track") != "u_local":
            continue
        frame = pd.read_parquet(path)
        frame = frame[frame["variant"].eq("raw")].copy()
        for key, value in task.items():
            frame[key] = value
        prediction_parts.append(frame)
    if not prediction_parts:
        return pd.DataFrame()

    predictions = pd.concat(prediction_parts, ignore_index=True)
    group_keys = [
        "stage",
        "model_name",
        "seed",
        "fold",
        "origin",
        "backend",
        "config_index",
    ]
    rows: list[dict[str, Any]] = []
    for key, group in predictions.groupby(group_keys, dropna=False):
        ordered = group.sort_values("unique_id", kind="stable")
        if ordered["unique_id"].nunique() != 5:
            continue
        actual = ordered["actual"].to_numpy(dtype=float)
        raw = ordered["prediction"].to_numpy(dtype=float)
        for variant, predicted in prediction_variants(raw).items():
            rows.append(
                {
                    **dict(zip(group_keys, key, strict=True)),
                    "track": "u_local_combined",
                    "position": None,
                    "variant": variant,
                    **score_draw_matrix(
                        actual.reshape(1, -1),
                        predicted.reshape(1, -1),
                    ),
                    "task_manifest": "COMBINED_FROM_U_LOCAL",
                }
            )
    return pd.DataFrame(rows)


def summarize_metrics(run_root: Path) -> dict[str, Any]:
    frame = collect_task_metrics(run_root)
    local_combined = _combined_local_metrics(run_root)
    if not local_combined.empty:
        frame = pd.concat([frame, local_combined], ignore_index=True)
    positions = collect_position_metrics(run_root)
    if frame.empty:
        return {"metric_rows": 0, "position_metric_rows": 0}

    if "config_index" not in frame.columns:
        frame["config_index"] = None

    frame.to_parquet(run_root / "evaluation_metrics.parquet", index=False)
    frame.to_csv(run_root / "evaluation_metrics.csv", index=False)
    if not positions.empty:
        positions.to_parquet(run_root / "position_metrics.parquet", index=False)
        positions.to_csv(run_root / "position_metrics.csv", index=False)

    metrics = [
        column
        for column in (
            "hit_pm1",
            "all_positions_hit_pm1",
            "exact_hit",
            "mae",
            "mse",
            "rmse",
        )
        if column in frame.columns
    ]
    candidate_columns = [
        "model_name",
        "track",
        "position",
        "config_index",
        "variant",
    ]
    group_columns = [*candidate_columns, "seed"]
    per_seed = frame.groupby(group_columns, dropna=False)[metrics].mean().reset_index()
    per_seed.to_parquet(run_root / "per_seed_metrics.parquet", index=False)
    per_seed.to_csv(run_root / "per_seed_metrics.csv", index=False)

    fold_frame = frame[frame["fold"].notna()].copy() if "fold" in frame.columns else pd.DataFrame()
    worst_fold = pd.DataFrame()
    if not fold_frame.empty:
        fold_columns = [*candidate_columns, "seed", "fold"]
        per_fold = fold_frame.groupby(fold_columns, dropna=False)[metrics].mean().reset_index()
        per_fold.to_parquet(run_root / "per_fold_metrics.parquet", index=False)
        per_fold.to_csv(run_root / "per_fold_metrics.csv", index=False)
        worst_fold = (
            per_fold.groupby(candidate_columns, dropna=False)["hit_pm1"]
            .min()
            .rename("worst_fold_hit_pm1")
            .reset_index()
        )

    aggregations = {metric: ["mean", "std", "min", "max"] for metric in metrics}
    seed_summary = per_seed.groupby(candidate_columns, dropna=False).agg(aggregations)
    seed_summary.columns = [f"{metric}_{stat}" for metric, stat in seed_summary.columns]
    seed_summary = seed_summary.reset_index()
    if "hit_pm1_min" in seed_summary.columns:
        seed_summary["worst_seed_hit_pm1"] = seed_summary["hit_pm1_min"]
    if not worst_fold.empty:
        seed_summary = seed_summary.merge(
            worst_fold,
            on=candidate_columns,
            how="left",
            validate="one_to_one",
        )
    else:
        seed_summary["worst_fold_hit_pm1"] = np.nan
    seed_summary.to_parquet(run_root / "seed_metric_summary.parquet", index=False)
    seed_summary.to_csv(run_root / "seed_metric_summary.csv", index=False)

    rank_columns = [
        "hit_pm1_mean",
        "all_positions_hit_pm1_mean",
        "mae_mean",
        "rmse_mean",
        "worst_seed_hit_pm1",
        "worst_fold_hit_pm1",
    ]
    if all(column in seed_summary.columns for column in rank_columns):
        ranking = seed_summary.sort_values(
            rank_columns,
            ascending=[False, False, True, True, False, False],
            kind="stable",
        ).reset_index(drop=True)
        ranking.insert(0, "rank", np.arange(1, len(ranking) + 1))
        ranking.to_parquet(run_root / "model_ranking.parquet", index=False)
        ranking.to_csv(run_root / "model_ranking.csv", index=False)

    return {
        "metric_rows": len(frame),
        "position_metric_rows": len(positions),
        "local_combined_rows": len(local_combined),
        "model_count": frame["model_name"].nunique(),
        "seed_count": frame["seed"].nunique(),
        "fold_count": (int(frame["fold"].dropna().nunique()) if "fold" in frame.columns else 0),
    }
