from __future__ import annotations

import json
import math
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .metrics import nearest_unique_sorted, score_draw_matrix, select_point_column
from .persistence import sha256_file, write_json, write_sha256s
from .tasks import CampaignTask

POSITION_IDS = ("P1", "P2", "P3", "P4", "P5")


@dataclass(frozen=True)
class AccuracySettings:
    promotion_per_position: int = 8
    promotion_max_total: int = 24
    promotion_global_candidates: int = 4
    min_validation_points: int = 20
    collapse_std_threshold: float = 0.20
    collapse_unique_ratio_threshold: float = 0.15
    max_models_per_position: int = 5
    min_oof_points: int = 10
    min_candidate_coverage: float = 0.90
    diversity_correlation_max: float = 0.995
    calibration_shrinkage: float = 20.0
    calibration_clip: float = 2.0
    calibration_min_hit_gain: float = 0.0
    calibration_min_mae_gain: float = 0.05
    decoder_alpha: float = 0.25
    decoder_distance_penalty: float = 0.02
    decoder_min_hit_gain: float = 0.0
    decoder_min_mae_gain: float = 0.05

    @classmethod
    def from_yaml(cls, path: Path) -> AccuracySettings:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise TypeError("accuracy configuration must be a mapping")
        unknown = set(payload) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown accuracy settings: {sorted(unknown)}")
        return cls(**payload)

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def task_signature(
    model_name: str,
    track: str,
    position: int | None,
) -> str:
    position_token = "all" if position is None else f"p{position}"
    return f"{model_name}|{track}|{position_token}"


def signature_from_task(task: CampaignTask) -> str:
    return task_signature(task.model_name, task.track, task.position)


def wilson_lower_bound(
    successes: int,
    total: int,
    *,
    z: float = 1.96,
) -> float:
    if total <= 0:
        return 0.0
    proportion = successes / total
    denominator = 1.0 + (z * z) / total
    centre = proportion + (z * z) / (2.0 * total)
    radius = z * math.sqrt(
        (proportion * (1.0 - proportion) / total) + (z * z) / (4.0 * total * total)
    )
    return max(0.0, (centre - radius) / denominator)


def _read_task_manifest(path: Path) -> dict[str, Any]:
    manifest = path.parent / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8"))


def _validate_prediction_frame(frame: pd.DataFrame) -> None:
    required = {"candidate_id", "unique_id", "prediction"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"prediction columns missing: {sorted(missing)}")
    prediction = pd.to_numeric(frame["prediction"], errors="raise")
    if not np.isfinite(prediction.to_numpy(dtype=float)).all():
        raise ValueError("non-finite predictions in accuracy input")
    if "actual" in frame.columns:
        actual = pd.to_numeric(frame["actual"], errors="raise")
        if not np.isfinite(actual.to_numpy(dtype=float)).all():
            raise ValueError("non-finite actuals in accuracy input")


def collect_scored_predictions(
    run_root: Path,
    *,
    expected_stage: str | None = None,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in sorted(run_root.glob("tasks/**/prediction_records.parquet")):
        payload = _read_task_manifest(path)
        if payload.get("status") != "PASS":
            continue
        task = CampaignTask(**payload["task"])
        if expected_stage is not None and task.stage != expected_stage:
            continue
        frame = pd.read_parquet(path)
        frame = frame[frame["variant"].eq("raw")].copy()
        frame = frame[frame["unique_id"].astype(str).isin(POSITION_IDS)].copy()
        if frame.empty:
            continue
        frame["model_name"] = task.model_name
        frame["track"] = task.track
        frame["task_position"] = task.position
        frame["seed"] = task.seed
        frame["fold"] = task.fold
        frame["origin"] = task.origin
        frame["config_index"] = task.config_index
        frame["candidate_id"] = signature_from_task(task)
        frame["task_manifest"] = str(path.parent / "manifest.json")
        rows.append(frame)
    if not rows:
        return pd.DataFrame()
    result = pd.concat(rows, ignore_index=True)
    _validate_prediction_frame(result)
    return result


def collect_prospective_predictions(run_root: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in sorted(run_root.glob("tasks/**/best_model/prediction_before_save.parquet")):
        task_root = path.parent.parent
        payload = json.loads((task_root / "manifest.json").read_text(encoding="utf-8"))
        if payload.get("status") != "PASS":
            continue
        task = CampaignTask(**payload["task"])
        if task.stage != "prospective":
            continue
        frame = pd.read_parquet(path)
        alias = f"{task.model_name}_{task.track}_s{task.seed}"
        point_column = select_point_column(frame, alias)
        one = frame[["unique_id", "ds", point_column]].copy()
        one = one[one["unique_id"].astype(str).isin(POSITION_IDS)].copy()
        one = one.rename(columns={point_column: "prediction", "ds": "origin"})
        one["model_name"] = task.model_name
        one["track"] = task.track
        one["task_position"] = task.position
        one["seed"] = task.seed
        one["fold"] = None
        one["config_index"] = task.config_index
        one["candidate_id"] = signature_from_task(task)
        one["task_manifest"] = str(task_root / "manifest.json")
        rows.append(one)
    if not rows:
        return pd.DataFrame()
    result = pd.concat(rows, ignore_index=True)
    _validate_prediction_frame(result)
    return result


def _load_selected_config_indices(
    validation_run: Path,
) -> dict[tuple[str, str, int | None], int]:
    mapping: dict[tuple[str, str, int | None], int] = {}
    for path in sorted((validation_run / "selected_configs").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        config_index = payload.get("config_index")
        if config_index is None:
            continue
        position = payload.get("position")
        key = (
            str(payload["model_name"]),
            str(payload["track"]),
            None if position is None else int(position),
        )
        mapping[key] = int(config_index)
    if not mapping:
        raise ValueError("no validation-selected config indices found")
    return mapping


def _selected_validation_predictions(validation_run: Path) -> pd.DataFrame:
    frame = collect_scored_predictions(
        validation_run,
        expected_stage="validate-trials",
    )
    if frame.empty:
        raise ValueError("validation replay predictions are empty")
    mapping = _load_selected_config_indices(validation_run)

    def selected(row: pd.Series) -> bool:
        position = row["task_position"]
        key = (
            str(row["model_name"]),
            str(row["track"]),
            None if pd.isna(position) else int(position),
        )
        expected = mapping.get(key)
        return expected is not None and int(row["config_index"]) == expected

    mask = frame.apply(selected, axis=1)
    selected_frame = frame[mask].copy()
    if selected_frame.empty:
        raise ValueError("selected validation predictions are empty")
    return selected_frame


def _candidate_position_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keys = [
        "candidate_id",
        "model_name",
        "track",
        "task_position",
        "unique_id",
    ]
    for key, group in frame.groupby(keys, dropna=False):
        ordered = group.sort_values(["origin", "seed"], kind="stable")
        aggregate = (
            ordered.groupby("origin", dropna=False)
            .agg(actual=("actual", "first"), prediction=("prediction", "mean"))
            .reset_index()
        )
        actual = aggregate["actual"].to_numpy(dtype=float)
        prediction = aggregate["prediction"].to_numpy(dtype=float)
        rounded = np.clip(np.rint(prediction), 1, 31)
        absolute = np.abs(rounded - actual)
        hits = int(np.sum(absolute <= 1.0))
        count = int(len(aggregate))
        prediction_std = float(np.std(prediction)) if count else 0.0
        rounded_unique = int(pd.Series(rounded).nunique())
        unique_ratio = rounded_unique / count if count else 0.0
        rows.append(
            {
                **dict(zip(keys, key, strict=True)),
                "points": count,
                "hits_pm1": hits,
                "hit_pm1": hits / count if count else 0.0,
                "hit_pm1_lcb": wilson_lower_bound(hits, count),
                "mae": float(np.mean(absolute)) if count else float("inf"),
                "mse": float(np.mean((rounded - actual) ** 2)) if count else float("inf"),
                "rmse": float(np.sqrt(np.mean((rounded - actual) ** 2))) if count else float("inf"),
                "prediction_std": prediction_std,
                "rounded_unique": rounded_unique,
                "unique_ratio": unique_ratio,
            }
        )
    return pd.DataFrame(rows)


def prepare_promotion_plan(
    validation_run: Path,
    output: Path,
    settings: AccuracySettings,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    frame = _selected_validation_predictions(validation_run)
    metrics = _candidate_position_metrics(frame)
    if metrics.empty:
        raise ValueError("no candidate metrics for promotion")
    metrics["collapsed"] = (
        (metrics["prediction_std"] < settings.collapse_std_threshold)
        & (metrics["unique_ratio"] < settings.collapse_unique_ratio_threshold)
        & (metrics["points"] >= settings.min_validation_points)
    )
    metrics["selection_score"] = (
        metrics["hit_pm1_lcb"] - 0.01 * metrics["mae"] - 0.05 * metrics["collapsed"].astype(float)
    )
    metrics.to_parquet(output / "validation_candidate_metrics.parquet", index=False)
    metrics.to_csv(output / "validation_candidate_metrics.csv", index=False)

    ranked_by_position: dict[str, list[dict[str, Any]]] = {}
    proposals: list[tuple[int, str, str]] = []
    for position in POSITION_IDS:
        group = metrics[metrics["unique_id"].eq(position)].copy()
        group = group[group["points"] >= settings.min_validation_points]
        group = group.sort_values(
            [
                "collapsed",
                "hit_pm1_lcb",
                "hit_pm1",
                "mae",
                "rmse",
                "candidate_id",
            ],
            ascending=[True, False, False, True, True, True],
            kind="stable",
        ).reset_index(drop=True)
        ranked_by_position[position] = group.to_dict(orient="records")
        for rank, row in group.head(settings.promotion_per_position).iterrows():
            proposals.append((int(rank), position, str(row["candidate_id"])))

    global_group = (
        metrics.groupby(
            ["candidate_id", "model_name", "track", "task_position"],
            dropna=False,
        )
        .agg(
            positions=("unique_id", "nunique"),
            hit_pm1_lcb=("hit_pm1_lcb", "mean"),
            hit_pm1=("hit_pm1", "mean"),
            mae=("mae", "mean"),
            collapsed_positions=("collapsed", "sum"),
        )
        .reset_index()
        .sort_values(
            [
                "collapsed_positions",
                "positions",
                "hit_pm1_lcb",
                "hit_pm1",
                "mae",
                "candidate_id",
            ],
            ascending=[True, False, False, False, True, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    for rank, row in global_group.head(settings.promotion_global_candidates).iterrows():
        proposals.append((int(rank), "GLOBAL", str(row["candidate_id"])))

    chosen: list[str] = []
    # Guarantee at least one candidate for every position.
    for position in POSITION_IDS:
        rows = ranked_by_position[position]
        if not rows:
            raise ValueError(f"no promotable candidate for {position}")
        candidate = str(rows[0]["candidate_id"])
        if candidate not in chosen:
            chosen.append(candidate)

    for _, _, candidate in sorted(proposals, key=lambda item: (item[0], item[1], item[2])):
        if candidate in chosen:
            continue
        if len(chosen) >= settings.promotion_max_total:
            break
        chosen.append(candidate)

    per_position_candidates = {
        position: [
            str(row["candidate_id"])
            for row in ranked_by_position[position]
            if str(row["candidate_id"]) in chosen
        ][: settings.promotion_per_position]
        for position in POSITION_IDS
    }
    for position, candidates in per_position_candidates.items():
        if not candidates:
            raise AssertionError(f"promotion lost all candidates for {position}")

    plan = {
        "schema_version": "all-auto-accuracy-promotion-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "fit_source": str(validation_run.resolve()),
        "holdout_used": False,
        "baseline_models_included": False,
        "ranking_scope": "auto_models_only",
        "settings": settings.as_dict(),
        "allowed_task_signatures": chosen,
        "per_position_candidates": per_position_candidates,
        "candidate_count": len(chosen),
        "status": "PASS",
    }
    write_json(output / "promotion_plan.json", plan)
    # The validation run remains the source for promoted OOF tasks. Copy the
    # immutable plan into that run and regenerate its complete SHA listing.
    shutil.copy2(output / "promotion_plan.json", validation_run / "promotion_plan.json")
    write_sha256s(validation_run)
    write_json(
        output / "manifest.json",
        {
            "status": "PASS",
            "stage": "accuracy-promotion",
            "candidate_count": len(chosen),
            "validation_points": int(len(frame)),
            "holdout_used": False,
        },
    )
    write_sha256s(output)
    return plan


def load_promotion_plan(source_run: Path) -> dict[str, Any] | None:
    candidates = [
        source_run / "promotion_plan.json",
        source_run / "accuracy_promotion" / "promotion_plan.json",
    ]
    for path in candidates:
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("status") != "PASS":
                raise ValueError(f"promotion plan not PASS: {path}")
            return payload
    return None


def filter_tasks_by_promotion(
    tasks: Sequence[CampaignTask],
    source_run: Path,
) -> list[CampaignTask]:
    plan = load_promotion_plan(source_run)
    if plan is None:
        return list(tasks)
    allowed = set(str(item) for item in plan["allowed_task_signatures"])
    filtered = [task for task in tasks if signature_from_task(task) in allowed]
    if not filtered:
        raise ValueError("promotion plan filtered every campaign task")
    return filtered


def _aggregate_seed_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    group_columns = [
        "candidate_id",
        "model_name",
        "track",
        "task_position",
        "fold",
        "origin",
        "unique_id",
    ]
    aggregate = (
        frame.groupby(group_columns, dropna=False)
        .agg(
            actual=("actual", "first"),
            prediction=("prediction", "mean"),
            seed_count=("seed", "nunique"),
            seed_std=("prediction", "std"),
        )
        .reset_index()
    )
    aggregate["seed_std"] = aggregate["seed_std"].fillna(0.0)
    return aggregate


def _robust_bias(
    residuals: np.ndarray,
    settings: AccuracySettings,
) -> float:
    values = np.asarray(residuals, dtype=float)
    if values.size == 0:
        return 0.0
    shrink = values.size / (values.size + settings.calibration_shrinkage)
    bias = float(np.median(values)) * shrink
    return float(np.clip(bias, -settings.calibration_clip, settings.calibration_clip))


def _score_vector(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    rounded = np.clip(np.rint(predicted), 1, 31)
    error = rounded - actual
    absolute = np.abs(error)
    hits = int(np.sum(absolute <= 1.0))
    count = int(actual.size)
    return {
        "count": float(count),
        "hits_pm1": float(hits),
        "hit_pm1": float(hits / count) if count else 0.0,
        "hit_pm1_lcb": wilson_lower_bound(hits, count),
        "mae": float(np.mean(absolute)) if count else float("inf"),
        "mse": float(np.mean(error**2)) if count else float("inf"),
        "rmse": float(np.sqrt(np.mean(error**2))) if count else float("inf"),
        "exact_hit": float(np.mean(absolute == 0.0)) if count else 0.0,
    }


def _calibrate_candidates(
    aggregate: pd.DataFrame,
    settings: AccuracySettings,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_parts: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    group_columns = [
        "candidate_id",
        "model_name",
        "track",
        "task_position",
        "unique_id",
    ]
    for key, group in aggregate.groupby(group_columns, dropna=False):
        group = group.sort_values(["fold", "origin"], kind="stable").copy()
        actual = group["actual"].to_numpy(dtype=float)
        raw = group["prediction"].to_numpy(dtype=float)
        folds = group["fold"].to_numpy()
        crossfit = raw.copy()
        for fold in pd.unique(group["fold"]):
            test_mask = folds == fold
            train_mask = ~test_mask
            bias = _robust_bias(actual[train_mask] - raw[train_mask], settings)
            crossfit[test_mask] = raw[test_mask] + bias
        base_metrics = _score_vector(actual, raw)
        calibrated_metrics = _score_vector(actual, crossfit)
        enable = bool(
            calibrated_metrics["hit_pm1"]
            > base_metrics["hit_pm1"] + settings.calibration_min_hit_gain
            or (
                math.isclose(
                    calibrated_metrics["hit_pm1"],
                    base_metrics["hit_pm1"],
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                and calibrated_metrics["mae"]
                <= base_metrics["mae"] - settings.calibration_min_mae_gain
            )
        )
        final_bias = _robust_bias(actual - raw, settings) if enable else 0.0
        group["crossfit_prediction"] = crossfit if enable else raw
        group["final_bias"] = final_bias
        group["calibration_enabled"] = enable
        output_parts.append(group)
        prediction_std = float(np.std(group["crossfit_prediction"]))
        rounded_unique = int(pd.Series(np.rint(group["crossfit_prediction"])).nunique())
        unique_ratio = rounded_unique / len(group) if len(group) else 0.0
        rows.append(
            {
                **dict(zip(group_columns, key, strict=True)),
                "points": len(group),
                "calibration_enabled": enable,
                "final_bias": final_bias,
                "prediction_std": prediction_std,
                "rounded_unique": rounded_unique,
                "unique_ratio": unique_ratio,
                "collapsed": bool(
                    prediction_std < settings.collapse_std_threshold
                    and unique_ratio < settings.collapse_unique_ratio_threshold
                ),
                **{f"base_{name}": value for name, value in base_metrics.items()},
                **{f"crossfit_{name}": value for name, value in calibrated_metrics.items()},
            }
        )
    return pd.concat(output_parts, ignore_index=True), pd.DataFrame(rows)


def _ensemble_method_predictions(
    matrix: pd.DataFrame,
    candidates: Sequence[str],
    method: str,
) -> np.ndarray:
    values = matrix[list(candidates)].to_numpy(dtype=float)
    if method == "median":
        return np.median(values, axis=1)
    if method == "mean":
        return np.mean(values, axis=1)
    raise ValueError(f"unsupported ensemble method: {method}")


def _score_key(metrics: dict[str, float]) -> tuple[float, float, float, float]:
    return (
        metrics["hit_pm1_lcb"],
        metrics["hit_pm1"],
        -metrics["mae"],
        -metrics["rmse"],
    )


def _choose_position_ensemble(
    frame: pd.DataFrame,
    position: str,
    settings: AccuracySettings,
) -> tuple[dict[str, Any], pd.DataFrame]:
    group = frame[frame["unique_id"].eq(position)].copy()
    if group.empty:
        raise ValueError(f"no OOF predictions for {position}")
    max_points = int(group.groupby("candidate_id").size().max())
    coverage = group.groupby("candidate_id").size() / max_points
    eligible = coverage[coverage >= settings.min_candidate_coverage].index.tolist()
    group = group[group["candidate_id"].isin(eligible)].copy()
    if group.empty:
        raise ValueError(f"no OOF candidates meet coverage for {position}")

    index_columns = ["fold", "origin"]
    actual_series = group.groupby(index_columns, dropna=False)["actual"].first().sort_index()
    matrix = group.pivot_table(
        index=index_columns,
        columns="candidate_id",
        values="crossfit_prediction",
        aggfunc="first",
    ).sort_index()
    common_index = matrix.dropna().index.intersection(actual_series.index)
    matrix = matrix.loc[common_index]
    actual = actual_series.loc[common_index].to_numpy(dtype=float)
    if len(matrix) < settings.min_oof_points:
        raise ValueError(f"insufficient common OOF points for {position}: {len(matrix)}")

    candidate_rows: list[dict[str, Any]] = []
    for candidate in matrix.columns:
        prediction = matrix[candidate].to_numpy(dtype=float)
        metrics = _score_vector(actual, prediction)
        prediction_std = float(np.std(prediction))
        unique_ratio = pd.Series(np.rint(prediction)).nunique() / len(prediction)
        collapsed = bool(
            prediction_std < settings.collapse_std_threshold
            and unique_ratio < settings.collapse_unique_ratio_threshold
        )
        candidate_rows.append(
            {
                "candidate_id": candidate,
                "collapsed": collapsed,
                "prediction_std": prediction_std,
                "unique_ratio": unique_ratio,
                **metrics,
            }
        )
    candidate_metrics = pd.DataFrame(candidate_rows).sort_values(
        ["collapsed", "hit_pm1_lcb", "hit_pm1", "mae", "rmse", "candidate_id"],
        ascending=[True, False, False, True, True, True],
        kind="stable",
    )
    selected = [str(candidate_metrics.iloc[0]["candidate_id"])]
    method = "mean"
    current_prediction = matrix[selected[0]].to_numpy(dtype=float)
    current_metrics = _score_vector(actual, current_prediction)

    remaining = [
        str(item)
        for item in candidate_metrics["candidate_id"].tolist()
        if str(item) not in selected
    ]
    while remaining and len(selected) < settings.max_models_per_position:
        best: (
            tuple[
                tuple[float, float, float, float],
                str,
                str,
                dict[str, float],
                np.ndarray,
            ]
            | None
        ) = None
        for candidate in remaining:
            correlations = [
                abs(
                    float(
                        np.corrcoef(
                            matrix[candidate].to_numpy(dtype=float),
                            matrix[chosen].to_numpy(dtype=float),
                        )[0, 1]
                    )
                )
                for chosen in selected
            ]
            for candidate_method in ("mean", "median"):
                proposed = [*selected, candidate]
                prediction = _ensemble_method_predictions(
                    matrix,
                    proposed,
                    candidate_method,
                )
                metrics = _score_vector(actual, prediction)
                improves = _score_key(metrics) > _score_key(current_metrics)
                if not improves:
                    continue
                if (
                    correlations
                    and min(correlations) > settings.diversity_correlation_max
                    and metrics["hit_pm1"] <= current_metrics["hit_pm1"]
                ):
                    continue
                item = (
                    _score_key(metrics),
                    candidate,
                    candidate_method,
                    metrics,
                    prediction,
                )
                if best is None or item[0] > best[0]:
                    best = item
        if best is None:
            break
        _, candidate, method, current_metrics, current_prediction = best
        selected.append(candidate)
        remaining.remove(candidate)

    output = pd.DataFrame(
        {
            "fold": [item[0] for item in matrix.index],
            "origin": [item[1] for item in matrix.index],
            "unique_id": position,
            "actual": actual,
            "ensemble_prediction": current_prediction,
        }
    )
    plan = {
        "position": position,
        "candidates": selected,
        "method": method,
        "oof_metrics": current_metrics,
        "common_oof_points": len(matrix),
    }
    return plan, output


def _pm1_candidate_scores(
    prediction: float,
    residuals: np.ndarray,
    settings: AccuracySettings,
    *,
    lower: int,
    upper: int,
) -> np.ndarray:
    candidates = np.arange(lower, upper + 1, dtype=float)
    residuals = np.asarray(residuals, dtype=float)
    if residuals.size == 0:
        residuals = np.array([0.0], dtype=float)
    simulated = prediction + residuals[:, None]
    hits = np.sum(np.abs(simulated - candidates[None, :]) <= 1.0, axis=0)
    probability = (hits + settings.decoder_alpha) / (
        residuals.size + settings.decoder_alpha * len(candidates)
    )
    residual_centre = float(np.median(residuals))
    scale = max(
        1.0,
        float(np.median(np.abs(residuals - residual_centre))),
    )
    distance = np.abs(candidates - (prediction + residual_centre)) / scale
    return np.log(np.maximum(probability, 1e-12)) - (settings.decoder_distance_penalty * distance)


def decode_pm1_sequence(
    predictions: np.ndarray,
    residual_samples: Sequence[Sequence[float]],
    settings: AccuracySettings,
    *,
    lower: int = 1,
    upper: int = 31,
) -> np.ndarray:
    raw = np.asarray(predictions, dtype=float).reshape(-1)
    if len(raw) != len(residual_samples):
        raise ValueError("decoder residual count does not match prediction count")
    numbers = np.arange(lower, upper + 1, dtype=int)
    score_matrix = np.vstack(
        [
            _pm1_candidate_scores(
                prediction,
                np.asarray(residuals, dtype=float),
                settings,
                lower=lower,
                upper=upper,
            )
            for prediction, residuals in zip(raw, residual_samples, strict=True)
        ]
    )
    count = len(raw)
    negative_infinity = -float("inf")
    dp = np.full((count, len(numbers)), negative_infinity, dtype=float)
    previous = np.full((count, len(numbers)), -1, dtype=int)
    dp[0] = score_matrix[0]
    for position in range(1, count):
        best_score = negative_infinity
        best_index = -1
        for index in range(len(numbers)):
            candidate = index - 1
            if candidate >= 0 and dp[position - 1, candidate] > best_score:
                best_score = dp[position - 1, candidate]
                best_index = candidate
            if best_index >= 0:
                dp[position, index] = best_score + score_matrix[position, index]
                previous[position, index] = best_index
    last_index: int = int(np.argmax(dp[-1]))
    if not np.isfinite(dp[-1, last_index]):
        raise RuntimeError("PM1 decoder failed")
    chosen: list[int] = [last_index]
    for position_index in range(count - 1, 0, -1):
        last_index = int(previous[position_index, last_index])
        chosen.append(last_index)
    chosen.reverse()
    return numbers[np.asarray(chosen, dtype=int)].astype(float)


def _joint_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    return score_draw_matrix(actual, predicted)


def _crossfit_decoder(
    ensemble: pd.DataFrame,
    settings: AccuracySettings,
) -> tuple[dict[str, Any], pd.DataFrame]:
    prediction_matrix = ensemble.pivot_table(
        index=["fold", "origin"],
        columns="unique_id",
        values="ensemble_prediction",
        aggfunc="first",
    )[list(POSITION_IDS)].sort_index()
    actual_matrix = ensemble.pivot_table(
        index=["fold", "origin"],
        columns="unique_id",
        values="actual",
        aggfunc="first",
    )[list(POSITION_IDS)].sort_index()
    common = prediction_matrix.dropna().index.intersection(actual_matrix.dropna().index)
    prediction_matrix = prediction_matrix.loc[common]
    actual_matrix = actual_matrix.loc[common]
    raw = prediction_matrix.to_numpy(dtype=float)
    actual = actual_matrix.to_numpy(dtype=float)
    base = np.vstack([nearest_unique_sorted(row) for row in raw])
    decoded = np.zeros_like(base)
    folds = np.asarray([index[0] for index in common])
    for fold in pd.unique(folds):
        test_mask = folds == fold
        train_mask = ~test_mask
        residuals = [
            (actual[train_mask, position] - raw[train_mask, position]).tolist()
            for position in range(len(POSITION_IDS))
        ]
        for row_index in np.flatnonzero(test_mask):
            decoded[row_index] = decode_pm1_sequence(
                raw[row_index],
                residuals,
                settings,
            )
    base_metrics = _joint_metrics(actual, base)
    decoded_metrics = _joint_metrics(actual, decoded)
    enable = bool(
        decoded_metrics["hit_pm1"] > base_metrics["hit_pm1"] + settings.decoder_min_hit_gain
        or (
            math.isclose(
                decoded_metrics["hit_pm1"],
                base_metrics["hit_pm1"],
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            and decoded_metrics["mae"] <= base_metrics["mae"] - settings.decoder_min_mae_gain
            and decoded_metrics["all_positions_hit_pm1"] >= base_metrics["all_positions_hit_pm1"]
        )
    )
    final_residuals = [
        (actual[:, position] - raw[:, position]).tolist() for position in range(len(POSITION_IDS))
    ]
    rows: list[dict[str, Any]] = []
    selected = decoded if enable else base
    for row_index, (fold, origin) in enumerate(common):
        for position_index, position in enumerate(POSITION_IDS):
            rows.append(
                {
                    "fold": fold,
                    "origin": origin,
                    "position": position,
                    "actual": float(actual[row_index, position_index]),
                    "ensemble_prediction": float(raw[row_index, position_index]),
                    "base_reconciled": float(base[row_index, position_index]),
                    "pm1_decoded": float(decoded[row_index, position_index]),
                    "selected_prediction": float(selected[row_index, position_index]),
                }
            )
    return (
        {
            "enabled": enable,
            "base_metrics": base_metrics,
            "crossfit_decoder_metrics": decoded_metrics,
            "residual_samples": final_residuals,
            "positions": list(POSITION_IDS),
        },
        pd.DataFrame(rows),
    )


def fit_accuracy_policy(
    validation_run: Path,
    oof_run: Path,
    output: Path,
    settings: AccuracySettings,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    promotion_source = validation_run / "accuracy_promotion" / "promotion_plan.json"
    if not promotion_source.is_file():
        promotion_source = validation_run / "promotion_plan.json"
    if not promotion_source.is_file():
        raise FileNotFoundError("validation promotion plan missing")
    promotion = json.loads(promotion_source.read_text(encoding="utf-8"))
    if promotion.get("holdout_used") is not False:
        raise ValueError("promotion plan is not Train/Validation-only")

    predictions = collect_scored_predictions(oof_run, expected_stage="oof")
    if predictions.empty:
        raise ValueError("OOF predictions are empty")
    allowed = set(str(item) for item in promotion["allowed_task_signatures"])
    predictions = predictions[predictions["candidate_id"].isin(allowed)].copy()
    if predictions.empty:
        raise ValueError("promotion candidates are missing from OOF")
    aggregate = _aggregate_seed_predictions(predictions)
    calibrated, calibration_metrics = _calibrate_candidates(aggregate, settings)
    calibration_metrics.to_parquet(
        output / "candidate_calibration_metrics.parquet",
        index=False,
    )
    calibration_metrics.to_csv(
        output / "candidate_calibration_metrics.csv",
        index=False,
    )

    position_plans: dict[str, Any] = {}
    ensemble_parts: list[pd.DataFrame] = []
    for position in POSITION_IDS:
        plan, frame = _choose_position_ensemble(
            calibrated,
            position,
            settings,
        )
        position_plans[position] = plan
        ensemble_parts.append(frame)
    ensemble = pd.concat(ensemble_parts, ignore_index=True)
    decoder_plan, decoder_rows = _crossfit_decoder(ensemble, settings)
    decoder_rows.to_parquet(output / "oof_accuracy_predictions.parquet", index=False)
    decoder_rows.to_csv(output / "oof_accuracy_predictions.csv", index=False)

    calibration_lookup: dict[str, dict[str, dict[str, float | bool]]] = {}
    for row in calibration_metrics.to_dict(orient="records"):
        candidate = str(row["candidate_id"])
        position = str(row["unique_id"])
        calibration_lookup.setdefault(candidate, {})[position] = {
            "enabled": bool(row["calibration_enabled"]),
            "bias": float(row["final_bias"]),
        }

    policy = {
        "schema_version": "all-auto-accuracy-policy-v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "validation_run": str(validation_run.resolve()),
        "oof_run": str(oof_run.resolve()),
        "fit_source_stages": ["validate-trials", "oof"],
        "holdout_used": False,
        "baseline_models_included": False,
        "ranking_scope": "auto_models_only",
        "settings": settings.as_dict(),
        "promotion_plan_sha256": sha256_file(promotion_source),
        "position_plans": position_plans,
        "calibration": calibration_lookup,
        "decoder": decoder_plan,
    }
    write_json(output / "accuracy_policy.json", policy)
    write_json(
        output / "manifest.json",
        {
            "status": "PASS",
            "stage": "accuracy-policy",
            "candidate_count": len(allowed),
            "position_count": len(position_plans),
            "decoder_enabled": decoder_plan["enabled"],
            "holdout_used": False,
        },
    )
    write_sha256s(output)

    # Make the OOF run the source of truth for later Holdout and Prospective.
    selected_source = validation_run / "selected_configs"
    selected_target = oof_run / "selected_configs"
    if selected_target.exists():
        shutil.rmtree(selected_target)
    shutil.copytree(selected_source, selected_target)
    shutil.copy2(promotion_source, oof_run / "promotion_plan.json")
    shutil.copy2(output / "accuracy_policy.json", oof_run / "accuracy_policy.json")
    write_sha256s(oof_run)
    return policy


def _aggregate_application_predictions(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "candidate_id",
        "model_name",
        "track",
        "task_position",
        "origin",
        "unique_id",
    ]
    aggregations: dict[str, tuple[str, str]] = {
        "prediction": ("prediction", "mean"),
        "seed_count": ("seed", "nunique"),
        "seed_std": ("prediction", "std"),
    }
    if "actual" in frame.columns:
        aggregations["actual"] = ("actual", "first")
    result = frame.groupby(columns, dropna=False).agg(**aggregations).reset_index()
    result["seed_std"] = result["seed_std"].fillna(0.0)
    return result


def _apply_position_plan(
    aggregate: pd.DataFrame,
    policy: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    calibration = policy["calibration"]
    for position in POSITION_IDS:
        plan = policy["position_plans"][position]
        candidates = [str(item) for item in plan["candidates"]]
        subset = aggregate[
            aggregate["unique_id"].eq(position) & aggregate["candidate_id"].isin(candidates)
        ].copy()
        if subset.empty:
            raise ValueError(f"no application predictions for {position}")
        for candidate in candidates:
            candidate_frame = subset[subset["candidate_id"].eq(candidate)]
            if candidate_frame.empty:
                raise ValueError(f"policy candidate missing: {candidate} {position}")
        for origin, origin_group in subset.groupby("origin", dropna=False):
            values: list[float] = []
            actual_values: list[float] = []
            for candidate in candidates:
                one = origin_group[origin_group["candidate_id"].eq(candidate)]
                if len(one) != 1:
                    raise ValueError(
                        f"candidate multiplicity for {candidate} {position} {origin}: {len(one)}"
                    )
                prediction = float(one.iloc[0]["prediction"])
                bias_payload = calibration.get(candidate, {}).get(
                    position,
                    {"enabled": False, "bias": 0.0},
                )
                if bias_payload.get("enabled"):
                    prediction += float(bias_payload.get("bias", 0.0))
                values.append(prediction)
                if "actual" in one.columns:
                    actual_values.append(float(one.iloc[0]["actual"]))
            method = str(plan["method"])
            ensemble_prediction = (
                float(np.median(values)) if method == "median" else float(np.mean(values))
            )
            row: dict[str, Any] = {
                "origin": origin,
                "position": position,
                "ensemble_prediction": ensemble_prediction,
                "candidate_count": len(candidates),
                "method": method,
            }
            if actual_values:
                if not np.allclose(actual_values, actual_values[0]):
                    raise ValueError(f"actual mismatch for {position} {origin}")
                row["actual"] = actual_values[0]
            rows.append(row)
    return pd.DataFrame(rows)


def _decode_application(
    position_frame: pd.DataFrame,
    policy: dict[str, Any],
    settings: AccuracySettings,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    decoder = policy["decoder"]
    residual_samples = decoder["residual_samples"]
    for _origin, group in position_frame.groupby("origin", dropna=False):
        ordered = group.set_index("position").loc[list(POSITION_IDS)].reset_index()
        raw = ordered["ensemble_prediction"].to_numpy(dtype=float)
        if decoder.get("enabled"):
            final = decode_pm1_sequence(raw, residual_samples, settings)
            decoder_name = "empirical_pm1"
        else:
            final = nearest_unique_sorted(raw)
            decoder_name = "nearest_unique_sorted"
        for index, _position in enumerate(POSITION_IDS):
            row = ordered.iloc[index].to_dict()
            row["final_prediction"] = float(final[index])
            row["decoder"] = decoder_name
            rows.append(row)
    return pd.DataFrame(rows)


def _metrics_from_decoded(frame: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    actual_matrix = frame.pivot_table(
        index="origin",
        columns="position",
        values="actual",
        aggfunc="first",
    )[list(POSITION_IDS)]
    predicted_matrix = frame.pivot_table(
        index="origin",
        columns="position",
        values="final_prediction",
        aggfunc="first",
    )[list(POSITION_IDS)]
    common = actual_matrix.dropna().index.intersection(predicted_matrix.dropna().index)
    actual = actual_matrix.loc[common].to_numpy(dtype=float)
    predicted = predicted_matrix.loc[common].to_numpy(dtype=float)
    overall = _joint_metrics(actual, predicted)
    overall["draws"] = len(common)
    for index, position in enumerate(POSITION_IDS):
        metrics = _score_vector(actual[:, index], predicted[:, index])
        rows.append({"position": position, **metrics})
    return overall, pd.DataFrame(rows)


def _write_auto_only_ranking(
    run_root: Path,
    ensemble_metrics: dict[str, Any],
    output: Path,
) -> None:
    model_path = run_root / "evaluation_metrics.parquet"
    rows: list[pd.DataFrame] = []
    if model_path.is_file():
        model_metrics = pd.read_parquet(model_path)
        if "model_name" in model_metrics.columns:
            model_metrics = model_metrics[
                ~model_metrics["model_name"].astype(str).str.startswith("baseline_")
            ].copy()
        score_columns = [
            "hit_pm1",
            "all_positions_hit_pm1",
            "exact_hit",
            "mae",
            "mse",
            "rmse",
        ]
        available = [column for column in score_columns if column in model_metrics.columns]
        if available:
            summary = (
                model_metrics.groupby(
                    ["model_name", "track", "variant"],
                    dropna=False,
                )[available]
                .mean()
                .reset_index()
                .rename(columns={"model_name": "model"})
            )
            summary["source"] = "NeuralForecastAuto"
            rows.append(summary)
    ensemble = pd.DataFrame(
        [
            {
                "model": "auto_accuracy_ensemble",
                "track": "oof_learned_position_ensemble",
                "variant": "pm1_decoded",
                **{
                    key: ensemble_metrics.get(key)
                    for key in (
                        "hit_pm1",
                        "all_positions_hit_pm1",
                        "exact_hit",
                        "mae",
                        "mse",
                        "rmse",
                    )
                },
                "source": "OOFAccuracyPolicy",
            }
        ]
    )
    rows.append(ensemble)
    ranking = pd.concat(rows, ignore_index=True, sort=False)
    ranking = ranking.sort_values(
        ["hit_pm1", "all_positions_hit_pm1", "mae", "rmse"],
        ascending=[False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    ranking.insert(0, "rank", np.arange(1, len(ranking) + 1))
    if ranking["model"].astype(str).str.startswith("baseline_").any():
        raise AssertionError("baseline leaked into formal auto-only ranking")
    ranking.to_parquet(output / "formal_auto_model_ranking.parquet", index=False)
    ranking.to_csv(output / "formal_auto_model_ranking.csv", index=False)


def apply_accuracy_policy(
    run_root: Path,
    policy_path: Path,
    output: Path,
    settings: AccuracySettings,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("status") != "PASS" or policy.get("holdout_used") is not False:
        raise ValueError("invalid or leaky accuracy policy")
    stage_manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    stage = str(stage_manifest.get("stage"))
    if stage == "prospective":
        predictions = collect_prospective_predictions(run_root)
    else:
        predictions = collect_scored_predictions(run_root, expected_stage=stage)
    if predictions.empty:
        raise ValueError(f"no predictions available for accuracy application: {stage}")
    aggregate = _aggregate_application_predictions(predictions)
    position_frame = _apply_position_plan(aggregate, policy)
    decoded = _decode_application(position_frame, policy, settings)
    decoded.to_parquet(output / "accuracy_predictions.parquet", index=False)
    decoded.to_csv(output / "accuracy_predictions.csv", index=False)

    metrics: dict[str, Any] | None = None
    if "actual" in decoded.columns:
        metrics, position_metrics = _metrics_from_decoded(decoded)
        write_json(output / "accuracy_metrics.json", metrics)
        position_metrics.to_parquet(
            output / "accuracy_position_metrics.parquet",
            index=False,
        )
        position_metrics.to_csv(
            output / "accuracy_position_metrics.csv",
            index=False,
        )
        _write_auto_only_ranking(run_root, metrics, output)
    else:
        freeze_payload = {
            "frozen_at": datetime.now(UTC).isoformat(),
            "actual_known": False,
            "prediction_sha256": sha256_file(output / "accuracy_predictions.parquet"),
            "policy_sha256": sha256_file(policy_path),
            "stage": stage,
        }
        write_json(output / "prediction_freeze.json", freeze_payload)

    manifest = {
        "schema_version": "all-auto-accuracy-application-v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "stage": stage,
        "run_root": str(run_root.resolve()),
        "policy": str(policy_path.resolve()),
        "policy_sha256": sha256_file(policy_path),
        "holdout_used_for_policy_fit": False,
        "baseline_models_included": False,
        "ranking_scope": "auto_models_only",
        "prediction_rows": len(decoded),
        "metrics": metrics,
    }
    write_json(output / "manifest.json", manifest)
    write_sha256s(output)
    return manifest
