from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .evaluation_artifacts import _sha256_file
from .evaluation_baselines import (
    _as_matrix,
    _baseline_registry,
    _postprocess,
    _validate_history,
)
from .evaluation_contracts import (
    EvaluationResult,
    Fold,
    OOFConfig,
    Predictor,
    _canonical_sha256,
    build_rolling_folds,
)
from .evaluation_metrics import (
    _point_metrics,
    _position_metrics,
    _probabilistic_metrics,
    _validate_prediction,
)


def _prediction_rows(
    *,
    fold: Fold,
    candidate: str,
    seed: int | None,
    positions: Sequence[str],
    actual: np.ndarray,
    raw_point: np.ndarray,
    point: np.ndarray,
    quantiles: Mapping[float, np.ndarray],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for position_index, position in enumerate(positions):
        for horizon_index in range(actual.shape[1]):
            row: dict[str, Any] = {
                "fold_id": fold.fold_id,
                "candidate": candidate,
                "seed": seed,
                "position": position,
                "horizon_step": horizon_index + 1,
                "actual": float(actual[position_index, horizon_index]),
                "raw_point": float(raw_point[position_index, horizon_index]),
                "point": float(point[position_index, horizon_index]),
                "prediction_variant": "reconciled",
            }
            for level, matrix in quantiles.items():
                row[f"q_{level}"] = float(matrix[position_index, horizon_index])
            rows.append(row)
    return rows


def _metric_row(
    *,
    fold: Fold,
    candidate: str,
    seed: int | None,
    actual: np.ndarray,
    point: np.ndarray,
    quantiles: Mapping[float, np.ndarray],
) -> dict[str, Any]:
    return {
        "fold_id": fold.fold_id,
        "candidate": candidate,
        "seed": seed,
        **_point_metrics(actual, point),
        **_probabilistic_metrics(actual, quantiles),
    }


def _aggregate_seed_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    numeric = [
        "hit_at_1",
        "all_position_hit_at_1",
        "mae",
        "mse",
        "rmse",
        "pinball_loss",
        "crps_approx",
        "coverage_80",
        "coverage_90",
        "interval_width_80",
        "interval_width_90",
        "calibration_error",
        "quantile_crossing_count",
    ]
    rows: list[dict[str, Any]] = []
    for candidate, group in metrics.groupby("candidate", sort=True):
        seeded = group.dropna(subset=["seed"]).copy()
        seed_hit = (
            seeded.groupby("seed", sort=True)["hit_at_1"].mean()
            if not seeded.empty
            else pd.Series(dtype=float)
        )
        fold_hit = group.groupby("fold_id", sort=True)["hit_at_1"].mean()
        row: dict[str, Any] = {
            "candidate": candidate,
            "row_count": int(len(group)),
            "seed_count": int(len(seed_hit)),
            "fold_count": int(group["fold_id"].nunique()),
            "best_seed_only_selection": False,
            "seed_hit_at_1_mean": float(seed_hit.mean()) if not seed_hit.empty else None,
            "seed_hit_at_1_variance": (
                float(seed_hit.var(ddof=0)) if not seed_hit.empty else None
            ),
            "seed_hit_at_1_minimum": float(seed_hit.min()) if not seed_hit.empty else None,
            "seed_hit_at_1_maximum": float(seed_hit.max()) if not seed_hit.empty else None,
            "worst_seed_hit_at_1": float(seed_hit.min()) if not seed_hit.empty else None,
            "worst_fold_hit_at_1": float(fold_hit.min()),
        }
        for column in numeric:
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            row[f"{column}_mean"] = float(values.mean()) if not values.empty else None
            row[f"{column}_variance"] = (
                float(values.var(ddof=0)) if not values.empty else None
            )
            row[f"{column}_minimum"] = float(values.min()) if not values.empty else None
            row[f"{column}_maximum"] = float(values.max()) if not values.empty else None
        rows.append(row)
    return pd.DataFrame(rows)


def _baseline_comparison(seed_summary: pd.DataFrame) -> pd.DataFrame:
    if "chronos2" not in set(seed_summary["candidate"]):
        return pd.DataFrame(
            columns=[
                "baseline",
                "chronos2_hit_at_1",
                "baseline_hit_at_1",
                "delta_hit_at_1",
                "chronos2_mae",
                "baseline_mae",
                "delta_mae",
            ]
        )
    champion = seed_summary.loc[seed_summary["candidate"] == "chronos2"].iloc[0]
    rows: list[dict[str, Any]] = []
    for _, baseline in seed_summary.iterrows():
        if baseline["candidate"] == "chronos2":
            continue
        rows.append(
            {
                "baseline": baseline["candidate"],
                "chronos2_hit_at_1": champion["hit_at_1_mean"],
                "baseline_hit_at_1": baseline["hit_at_1_mean"],
                "delta_hit_at_1": (
                    champion["hit_at_1_mean"] - baseline["hit_at_1_mean"]
                ),
                "chronos2_mae": champion["mae_mean"],
                "baseline_mae": baseline["mae_mean"],
                "delta_mae": baseline["mae_mean"] - champion["mae_mean"],
            }
        )
    return pd.DataFrame(rows)


def run_oof_evaluation(
    history: pd.DataFrame,
    config: OOFConfig,
    predictor: Predictor,
) -> EvaluationResult:
    _validate_history(history, config)
    source = history.copy(deep=True)
    source_sha256 = _canonical_sha256(source.to_dict(orient="records"))
    folds = build_rolling_folds(len(source), config)
    baseline_registry = _baseline_registry()

    fold_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []

    for fold in folds:
        train = source.iloc[fold.train_start : fold.train_end].copy(deep=True)
        validation = source.iloc[fold.validation_start : fold.validation_end].copy(deep=True)
        actual = _as_matrix(validation, config.position_columns)
        train_sha256 = _canonical_sha256(train.to_dict(orient="records"))
        validation_sha256 = _canonical_sha256(validation.to_dict(orient="records"))
        fold_rows.append(
            {
                "fold_id": fold.fold_id,
                "train_start": fold.train_start,
                "train_end_exclusive": fold.train_end,
                "validation_start": fold.validation_start,
                "validation_end_exclusive": fold.validation_end,
                "train_rows": len(train),
                "validation_rows": len(validation),
                "train_sha256": train_sha256,
                "validation_sha256": validation_sha256,
                "chronology_verified": fold.train_end <= fold.validation_start,
            }
        )

        for seed in config.seeds:
            bundle = predictor(
                train.copy(deep=True),
                horizon=config.horizon,
                seed=seed,
                fold_id=fold.fold_id,
            )
            raw_point, quantiles = _validate_prediction(bundle, config)
            point = _postprocess(raw_point, config)
            prediction_rows.extend(
                _prediction_rows(
                    fold=fold,
                    candidate="chronos2",
                    seed=seed,
                    positions=config.position_columns,
                    actual=actual,
                    raw_point=raw_point,
                    point=point,
                    quantiles=quantiles,
                )
            )
            metric_rows.append(
                _metric_row(
                    fold=fold,
                    candidate="chronos2",
                    seed=seed,
                    actual=actual,
                    point=point,
                    quantiles=quantiles,
                )
            )
            for row in _position_metrics(actual, point):
                position_index = int(row.pop("position_index"))
                position_rows.append(
                    {
                        "fold_id": fold.fold_id,
                        "candidate": "chronos2",
                        "seed": seed,
                        "position": config.position_columns[position_index],
                        **row,
                    }
                )

        for name, baseline in baseline_registry.items():
            seeds: tuple[int | None, ...] = config.seeds if name == "random" else (None,)
            for seed in seeds:
                raw_point = baseline(train.copy(deep=True), config, seed)
                point = _postprocess(raw_point, config)
                prediction_rows.extend(
                    _prediction_rows(
                        fold=fold,
                        candidate=name,
                        seed=seed,
                        positions=config.position_columns,
                        actual=actual,
                        raw_point=raw_point,
                        point=point,
                        quantiles={},
                    )
                )
                metric_rows.append(
                    _metric_row(
                        fold=fold,
                        candidate=name,
                        seed=seed,
                        actual=actual,
                        point=point,
                        quantiles={},
                    )
                )
                for row in _position_metrics(actual, point):
                    position_index = int(row.pop("position_index"))
                    position_rows.append(
                        {
                            "fold_id": fold.fold_id,
                            "candidate": name,
                            "seed": seed,
                            "position": config.position_columns[position_index],
                            **row,
                        }
                    )

    if _canonical_sha256(history.to_dict(orient="records")) != source_sha256:
        raise RuntimeError("source history mutated during evaluation")

    folds_df = pd.DataFrame(fold_rows)
    predictions_df = pd.DataFrame(prediction_rows)
    metrics_df = pd.DataFrame(metric_rows)
    position_df = pd.DataFrame(position_rows)
    seed_summary = _aggregate_seed_metrics(metrics_df)
    comparison = _baseline_comparison(seed_summary)

    prediction_payload = predictions_df.to_dict(orient="records")
    metrics_payload = metrics_df.to_dict(orient="records")
    report = {
        "schema_version": 1,
        "run_id": config.run_id,
        "status": "PASS",
        "primary_metric": "Hit@±1",
        "source_sha256": source_sha256,
        "config_sha256": _canonical_sha256(config.model_dump(mode="json")),
        "prediction_values_sha256": _canonical_sha256(prediction_payload),
        "metrics_sha256": _canonical_sha256(metrics_payload),
        "evaluation_code_sha256": _sha256_file(Path(__file__)),
        "fold_count": len(folds),
        "position_count": len(config.position_columns),
        "horizon": config.horizon,
        "seeds": list(config.seeds),
        "candidate_count": int(seed_summary["candidate"].nunique()),
        "required_baselines": sorted(baseline_registry),
        "best_seed_only_selection": False,
        "holdout_opened": False,
        "prospective_opened": False,
        "train_only_fit": True,
        "validation_overlap_allowed": config.allow_validation_overlap,
        "point_postprocessing": "round_clip_unique_sort_v1",
        "raw_point_preserved": True,
    }
    return EvaluationResult(
        report=report,
        folds=folds_df,
        predictions=predictions_df,
        metrics=metrics_df,
        position_metrics=position_df,
        seed_summary=seed_summary,
        baseline_comparison=comparison,
    )
