"""Prediction extraction and metric aggregation for Prospective scoring."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .metrics import nearest_unique_sorted, score_draw_matrix, score_vector, select_point_column
from .persistence import sha256_file
from .prospective_scoring_support import (
    LOWER_BOUND,
    UPPER_BOUND,
    _require_regular_file,
    _safe_relative,
)


def _extract_locked_predictions(
    run_root: Path,
    lock: Mapping[str, Any],
    package_root: Path,
    number_columns: list[str],
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[int]]:
    tasks = lock.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("prediction lock tasks missing")
    rows: list[dict[str, Any]] = []
    copies: list[dict[str, Any]] = []
    expected_ds: list[int] | None = None
    for index, item in enumerate(tasks):
        if not isinstance(item, Mapping):
            raise ValueError(f"prediction lock task {index} is not an object")
        task_path = str(item.get("task_path") or "")
        task = item.get("task")
        files = item.get("files")
        if not isinstance(task, Mapping) or not isinstance(files, Mapping):
            raise ValueError(f"prediction lock task evidence incomplete: {task_path}")
        prediction_record = files.get("prediction_before")
        if not isinstance(prediction_record, Mapping):
            raise ValueError(f"prediction_before record missing: {task_path}")
        failures: list[str] = []
        relative = _safe_relative(
            str(prediction_record.get("path") or ""),
            failures,
            f"{task_path} prediction path",
        )
        if relative is None or failures:
            raise ValueError("; ".join(failures))
        source = run_root / relative
        _require_regular_file(source, f"{task_path} prediction")
        recorded_sha = str(prediction_record.get("sha256") or "")
        actual_sha = sha256_file(source)
        if actual_sha != recorded_sha:
            raise ValueError(f"locked prediction SHA mismatch: {task_path}")
        copy_relative = Path("source_predictions") / f"{index:05d}-{actual_sha[:16]}.parquet"
        copy_target = package_root / copy_relative
        copy_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy_target)
        if sha256_file(copy_target) != actual_sha:
            raise RuntimeError(f"prediction copy SHA mismatch: {task_path}")

        frame = pd.read_parquet(copy_target)
        required = {"unique_id", "ds"}
        if not required.issubset(frame.columns):
            raise ValueError(
                f"prediction columns missing for {task_path}: "
                f"required={sorted(required)}, actual={list(frame.columns)}"
            )
        alias = f"{task.get('model_name')}_{task.get('track')}_s{task.get('seed')}"
        point_column = select_point_column(frame, alias)
        filtered = frame[frame["unique_id"].astype(str).isin(number_columns)].copy()
        if filtered.empty:
            raise ValueError(f"no position predictions found: {task_path}")
        filtered["unique_id"] = filtered["unique_id"].astype(str)
        filtered["ds"] = pd.to_numeric(filtered["ds"], errors="raise").astype("int64")
        filtered["prediction"] = pd.to_numeric(
            filtered[point_column],
            errors="raise",
        ).astype(float)
        if not np.isfinite(filtered["prediction"].to_numpy()).all():
            raise ValueError(f"non-finite locked predictions: {task_path}")
        if filtered.duplicated(["ds", "unique_id"]).any():
            raise ValueError(f"duplicate prediction keys: {task_path}")
        task_ds = sorted(int(value) for value in filtered["ds"].unique())
        if expected_ds is None:
            expected_ds = task_ds
        elif task_ds != expected_ds:
            raise ValueError(
                f"prediction horizon mismatch: {task_path}; "
                f"expected={expected_ds}, actual={task_ds}"
            )

        position = task.get("position")
        track = str(task.get("track") or "")
        if track == "u_local":
            if not isinstance(position, int) or not 1 <= position <= len(number_columns):
                raise ValueError(f"invalid u_local position: {task_path}")
            expected_id = number_columns[position - 1]
            if set(filtered["unique_id"]) != {expected_id}:
                raise ValueError(
                    f"u_local unique_id mismatch: {task_path}; expected={expected_id}"
                )
        candidate_id = f"task:{task_path}"
        for record in filtered[["ds", "unique_id", "prediction"]].to_dict("records"):
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "task_path": task_path,
                    "source_type": "model",
                    "model_name": task.get("model_name"),
                    "baseline_name": None,
                    "track": track,
                    "position": position,
                    "seed": task.get("seed"),
                    "backend": task.get("backend"),
                    "config_index": task.get("config_index"),
                    **record,
                }
            )
        copies.append(
            {
                "task_path": task_path,
                "source_prediction_path": str(prediction_record.get("path")),
                "source_prediction_sha256": actual_sha,
                "copied_prediction_path": copy_relative.as_posix(),
                "copied_prediction_sha256": sha256_file(copy_target),
                "size_bytes": copy_target.stat().st_size,
                "point_column": point_column,
                "prediction_rows": len(filtered),
            }
        )
    if expected_ds is None or not expected_ds:
        raise ValueError("no prospective prediction horizon found")
    return pd.DataFrame(rows), copies, expected_ds


def _matrix_variants(
    matrix: np.ndarray,
    *,
    complete: bool,
) -> dict[str, np.ndarray]:
    raw = np.asarray(matrix, dtype=float)
    rounded = np.clip(np.rint(raw), LOWER_BOUND, UPPER_BOUND)
    variants = {"raw": raw, "rounded": rounded}
    if complete:
        variants["reconciled"] = np.vstack(
            [
                nearest_unique_sorted(
                    row,
                    lower=LOWER_BOUND,
                    upper=UPPER_BOUND,
                )
                for row in raw
            ]
        )
    return variants


def _candidate_metadata(frame: pd.DataFrame) -> dict[str, Any]:
    first = frame.iloc[0]
    return {
        "candidate_id": first["candidate_id"],
        "source_type": first["source_type"],
        "model_name": first.get("model_name"),
        "baseline_name": first.get("baseline_name"),
        "track": first.get("track"),
        "position": first.get("position"),
        "seed": first.get("seed"),
        "backend": first.get("backend"),
        "config_index": first.get("config_index"),
    }


def _score_candidates(
    predictions: pd.DataFrame,
    actuals: pd.DataFrame,
    *,
    number_columns: list[str],
    expected_ds: list[int],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    actual_matrix = (
        actuals.set_index("draw_index").loc[expected_ds, number_columns].to_numpy(dtype=float)
    )
    metric_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    variant_prediction_rows: list[dict[str, Any]] = []
    for _candidate_id, group in predictions.groupby("candidate_id", dropna=False, sort=True):
        metadata = _candidate_metadata(group)
        ids = [value for value in number_columns if value in set(group["unique_id"])]
        if not ids:
            raise ValueError(f"candidate has no known positions: {metadata['candidate_id']}")
        complete = ids == number_columns
        if not complete and metadata.get("track") != "u_local":
            raise ValueError(
                "non-local candidate is missing positions: "
                f"{metadata['candidate_id']}"
            )
        pivot = group.pivot(index="ds", columns="unique_id", values="prediction")
        if sorted(int(value) for value in pivot.index) != expected_ds:
            raise ValueError(f"candidate horizon mismatch: {metadata['candidate_id']}")
        if any(name not in pivot.columns for name in ids):
            raise ValueError(f"candidate position matrix incomplete: {metadata['candidate_id']}")
        predicted = pivot.loc[expected_ds, ids].to_numpy(dtype=float)
        actual = actual_matrix[:, [number_columns.index(name) for name in ids]]
        for variant, values in _matrix_variants(predicted, complete=complete).items():
            metrics = score_draw_matrix(actual, values)
            if not complete:
                metrics["all_positions_hit_pm1"] = float("nan")
            metric_rows.append(
                {
                    **metadata,
                    "variant": variant,
                    "complete_draw": complete,
                    **metrics,
                }
            )
            for position_index, unique_id in enumerate(ids):
                one = score_vector(actual[:, position_index], values[:, position_index])
                position_rows.append(
                    {
                        **metadata,
                        "variant": variant,
                        "unique_id": unique_id,
                        **one,
                    }
                )
                for row_index, draw_index in enumerate(expected_ds):
                    variant_prediction_rows.append(
                        {
                            **metadata,
                            "variant": variant,
                            "draw_index": draw_index,
                            "unique_id": unique_id,
                            "prediction": float(values[row_index, position_index]),
                            "actual": float(actual[row_index, position_index]),
                            "absolute_error": float(
                                abs(
                                    values[row_index, position_index]
                                    - actual[row_index, position_index]
                                )
                            ),
                            "hit_pm1": bool(
                                abs(
                                    values[row_index, position_index]
                                    - actual[row_index, position_index]
                                )
                                <= 1.0
                            ),
                        }
                    )
    return (
        pd.DataFrame(metric_rows),
        pd.DataFrame(position_rows),
        pd.DataFrame(variant_prediction_rows),
    )


def _add_combined_local_candidates(
    predictions: pd.DataFrame,
    number_columns: list[str],
) -> pd.DataFrame:
    local = predictions[predictions["track"].eq("u_local")].copy()
    if local.empty:
        return predictions
    group_columns = ["model_name", "seed", "backend", "config_index"]
    combined_rows: list[dict[str, Any]] = []
    for key, group in local.groupby(group_columns, dropna=False, sort=True):
        if set(group["unique_id"]) != set(number_columns):
            continue
        if group.duplicated(["ds", "unique_id"]).any():
            raise ValueError(f"duplicate local prediction keys: {key}")
        model_name, seed, backend, config_index = key
        candidate_id = (
            f"combined-local:{model_name}:seed={seed}:backend={backend}:"
            f"config={config_index}"
        )
        for record in group[["ds", "unique_id", "prediction"]].to_dict("records"):
            combined_rows.append(
                {
                    "candidate_id": candidate_id,
                    "task_path": "COMBINED_FROM_U_LOCAL",
                    "source_type": "model",
                    "model_name": model_name,
                    "baseline_name": None,
                    "track": "u_local_combined",
                    "position": None,
                    "seed": seed,
                    "backend": backend,
                    "config_index": config_index,
                    **record,
                }
            )
    if combined_rows:
        return pd.concat([predictions, pd.DataFrame(combined_rows)], ignore_index=True)
    return predictions


def _baseline_prediction_frame(
    baselines: Mapping[str, np.ndarray],
    *,
    expected_ds: list[int],
    number_columns: list[str],
    random_seed: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for name, matrix in baselines.items():
        candidate_id = f"baseline:{name}"
        seed = random_seed if name == "random_uniform" else None
        for draw_offset, draw_index in enumerate(expected_ds):
            for position, unique_id in enumerate(number_columns):
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "task_path": "BASELINE_HISTORY_ONLY",
                        "source_type": "baseline",
                        "model_name": None,
                        "baseline_name": name,
                        "track": "baseline",
                        "position": None,
                        "seed": seed,
                        "backend": "numpy",
                        "config_index": None,
                        "ds": draw_index,
                        "unique_id": unique_id,
                        "prediction": float(matrix[draw_offset, position]),
                    }
                )
    return pd.DataFrame(rows)


def _write_table(frame: pd.DataFrame, root: Path, stem: str) -> dict[str, Any]:
    parquet = root / f"{stem}.parquet"
    csv = root / f"{stem}.csv"
    frame.to_parquet(parquet, index=False)
    frame.to_csv(csv, index=False)
    return {
        "rows": len(frame),
        "parquet": {"path": parquet.name, "sha256": sha256_file(parquet)},
        "csv": {"path": csv.name, "sha256": sha256_file(csv)},
    }


def _seed_summary(
    metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    primary = metrics[
        (metrics["complete_draw"] & metrics["variant"].eq("reconciled"))
        | (~metrics["complete_draw"] & metrics["variant"].eq("rounded"))
    ].copy()
    group_columns = ["source_type", "model_name", "baseline_name", "track"]
    seed_columns = [*group_columns, "seed"]
    metric_columns = [
        "hit_pm1",
        "all_positions_hit_pm1",
        "mae",
        "mse",
        "rmse",
    ]
    per_seed = (
        primary.groupby(seed_columns, dropna=False)[metric_columns]
        .mean()
        .reset_index()
    )
    aggregations = {
        metric: ["mean", "std", "var", "min", "max"]
        for metric in metric_columns
    }
    summary = per_seed.groupby(group_columns, dropna=False).agg(aggregations)
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    summary = summary.reset_index()
    seed_counts = (
        per_seed.groupby(group_columns, dropna=False)
        .size()
        .rename("seed_count")
        .reset_index()
    )
    summary = summary.merge(
        seed_counts,
        on=group_columns,
        how="left",
        validate="one_to_one",
    )
    summary["worst_seed_hit_pm1"] = summary["hit_pm1_min"]
    complete = summary[summary["track"].ne("u_local")].copy()
    ranking = complete.sort_values(
        [
            "hit_pm1_mean",
            "all_positions_hit_pm1_mean",
            "mae_mean",
            "rmse_mean",
            "worst_seed_hit_pm1",
        ],
        ascending=[False, False, True, True, False],
        kind="stable",
    ).reset_index(drop=True)
    ranking.insert(0, "rank", np.arange(1, len(ranking) + 1))
    return per_seed, summary, ranking


def _baseline_comparison(ranking: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    model_rows = ranking[ranking["source_type"].eq("model")]
    baseline_rows = ranking[ranking["source_type"].eq("baseline")]
    if model_rows.empty:
        return pd.DataFrame(), None
    champion = model_rows.iloc[0]
    rows: list[dict[str, Any]] = []
    for _, baseline in baseline_rows.iterrows():
        rows.append(
            {
                "champion_model": champion["model_name"],
                "champion_track": champion["track"],
                "baseline": baseline["baseline_name"],
                "hit_pm1_delta": champion["hit_pm1_mean"] - baseline["hit_pm1_mean"],
                "all_positions_hit_pm1_delta": (
                    champion["all_positions_hit_pm1_mean"]
                    - baseline["all_positions_hit_pm1_mean"]
                ),
                "mae_improvement": baseline["mae_mean"] - champion["mae_mean"],
                "rmse_improvement": baseline["rmse_mean"] - champion["rmse_mean"],
            }
        )
    champion_payload = {
        "model_name": champion["model_name"],
        "track": champion["track"],
        "hit_pm1": float(champion["hit_pm1_mean"]),
        "all_positions_hit_pm1": float(champion["all_positions_hit_pm1_mean"]),
        "mae": float(champion["mae_mean"]),
        "mse": float(champion["mse_mean"]),
        "rmse": float(champion["rmse_mean"]),
        "worst_seed_hit_pm1": float(champion["worst_seed_hit_pm1"]),
    }
    return pd.DataFrame(rows), champion_payload
