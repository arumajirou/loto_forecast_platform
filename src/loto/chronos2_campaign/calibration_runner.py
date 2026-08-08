from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from .calibration_cells import (
    _cell_rows,
    _comparison,
    _fit_cell_parameters,
    _metric_row,
    _prediction_rows,
    _target_matrices,
)
from .calibration_contracts import CalibrationConfig, CalibrationResult, canonical_sha256
from .calibration_input import _geometry_config, _split_prior_folds, _validate_inputs
from .calibration_methods import rearrange_quantiles
from .evaluation_baselines import _postprocess
from .evaluation_metrics import _position_metrics
from .evaluation_runner import _aggregate_seed_metrics

_VARIANTS = (
    "chronos2_uncalibrated",
    "chronos2_bias_calibrated",
    "chronos2_bias_quantile_calibrated",
    "chronos2_bias_quantile_conformal",
)


def run_calibration_evaluation(
    predictions: pd.DataFrame,
    folds: pd.DataFrame,
    config: CalibrationConfig,
) -> CalibrationResult:
    predictions_original = predictions.copy(deep=True)
    folds_original = folds.copy(deep=True)
    source_prediction_sha256 = canonical_sha256(predictions.to_dict(orient="records"))
    source_fold_sha256 = canonical_sha256(folds.to_dict(orient="records"))
    selected, fold_table, fold_ids, seeds = _validate_inputs(predictions, folds, config)
    geometry = _geometry_config(config)

    split_rows: list[dict[str, Any]] = []
    parameter_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    eligible_fold_ids: list[str] = []
    warmup_fold_ids: list[str] = []
    total_rearrangements = 0

    fold_order = {fold_id: index for index, fold_id in enumerate(fold_ids)}
    for target_index, target_fold_id in enumerate(fold_ids):
        split = _split_prior_folds(fold_ids[:target_index], config)
        if split is None:
            warmup_fold_ids.append(target_fold_id)
            split_rows.append(
                {
                    "target_fold_id": target_fold_id,
                    "target_order": target_index,
                    "status": "NOT_APPLICABLE_WARMUP",
                    "fit_fold_ids": "[]",
                    "conformal_fold_ids": "[]",
                    "future_fold_count_used": 0,
                    "target_fold_excluded": True,
                    "chronology_verified": True,
                }
            )
            continue
        fit_ids, conformal_ids = split
        eligible_fold_ids.append(target_fold_id)
        chronology_verified = (
            max(fold_order[value] for value in fit_ids)
            < min(fold_order[value] for value in conformal_ids)
            < target_index
        )
        if not chronology_verified:
            raise RuntimeError("calibration split chronology violation")
        split_rows.append(
            {
                "target_fold_id": target_fold_id,
                "target_order": target_index,
                "status": "EVALUATED",
                "fit_fold_ids": json.dumps(fit_ids),
                "conformal_fold_ids": json.dumps(conformal_ids),
                "future_fold_count_used": 0,
                "target_fold_excluded": target_fold_id not in {*fit_ids, *conformal_ids},
                "chronology_verified": chronology_verified,
            }
        )

        for seed in seeds:
            actual, source_raw, source_point, source_quantiles = _target_matrices(
                selected,
                fold_id=target_fold_id,
                seed=seed,
                config=config,
            )
            bias_matrix = np.zeros_like(source_raw)
            correction_matrices = {
                level: np.zeros_like(source_raw) for level in config.quantile_levels
            }
            qhat_matrices = {
                coverage: np.zeros_like(source_raw) for coverage in config.interval_coverages
            }

            for position_index, position in enumerate(config.position_columns):
                for horizon_index in range(config.horizon):
                    horizon_step = horizon_index + 1
                    fit_rows = _cell_rows(
                        selected,
                        fold_ids=fit_ids,
                        seed=seed,
                        position=position,
                        horizon_step=horizon_step,
                    )
                    conformal_rows = _cell_rows(
                        selected,
                        fold_ids=conformal_ids,
                        seed=seed,
                        position=position,
                        horizon_step=horizon_step,
                    )
                    bias, corrections, qhats, rearrangements = _fit_cell_parameters(
                        fit_rows,
                        conformal_rows,
                        config,
                    )
                    total_rearrangements += rearrangements
                    bias_matrix[position_index, horizon_index] = bias
                    for level, value in corrections.items():
                        correction_matrices[level][position_index, horizon_index] = value
                    for coverage, value in qhats.items():
                        qhat_matrices[coverage][position_index, horizon_index] = value
                    parameter_rows.append(
                        {
                            "target_fold_id": target_fold_id,
                            "seed": seed,
                            "position": position,
                            "horizon_step": horizon_step,
                            "fit_fold_ids": json.dumps(fit_ids),
                            "conformal_fold_ids": json.dumps(conformal_ids),
                            "fit_row_count": len(fit_rows),
                            "conformal_row_count": len(conformal_rows),
                            "bias_offset": bias,
                            "quantile_corrections": json.dumps(
                                {str(level): value for level, value in corrections.items()},
                                sort_keys=True,
                            ),
                            "conformal_qhats": json.dumps(
                                {str(level): value for level, value in qhats.items()},
                                sort_keys=True,
                            ),
                            "fit_sha256": canonical_sha256(fit_rows.to_dict(orient="records")),
                            "conformal_sha256": canonical_shaa256(
                                conformal_rows.to_dict(orient="records")
                            ),
                            "target_fold_excluded": target_fold_id
                            not in {*fit_ids, *conformal_ids},
                            "future_fold_count_used": 0,
                        }
                    )

            bias_raw = source_raw + bias_matrix
            bias_point = _postprocess(bias_raw, geometry)
            quantile_calibrated = {
                level: source_quantiles[level] + correction_matrices[level]
                for level in config.quantile_levels
            }
            conformal_quantiles = {
                level: matrix.copy() for level, matrix in quantile_calibrated.items()
            }
            target_rearrangements = 0
            for position_index in range(len(config.position_columns)):
                for horizon_index in range(config.horizon):
                    cell = {
                        level: quantile_calibrated[level][position_index, horizon_index]
                        for level in config.quantile_levels
                    }
                    rearranged, changed = rearrange_quantiles(cell)
                    target_rearrangements += changed
                    for level, value in rearranged.items():
                        quantile_calibrated[level][position_index, horizon_index] = value
                        conformal_quantiles[level][position_index, horizon_index] = value
                    for coverage in config.interval_coverages:
                        alpha = 1.0 - coverage
                        lower_level = round(alpha / 2.0, 10)
                        upper_level = round(1.0 - alpha / 2.0, 10)
                        qhat = qhat_matrices[coverage][position_index, horizon_index]
                        conformal_quantiles[lower_level][position_index, horizon_index] -= qhat
                        conformal_quantiles[upper_level][position_index, horizon_index] += qhat
                    conformal_cell = {
                        level: conformal_quantiles[level][position_index, horizon_index]
                        for level in config.quantile_levels
                    }
                    rearranged_conformal, changed = rearrange_quantiles(conformal_cell)
                    target_rearrangements += changed
                    for level, value in rearranged_conformal.items():
                        conformal_quantiles[level][position_index, horizon_index] = value
            total_rearrangements += target_rearrangements

            variants: tuple[tuple[str, np.ndarray, Mapping[float, np.ndarray]], ...] = (
                ("chronos2_uncalibrated", source_point, source_quantiles),
                ("chronos2_bias_calibrated", bias_point, {}),
                (
                    "chronos2_bias_quantile_calibrated",
                    bias_point,
                    quantile_calibrated,
                ),
                (
                    "chronos2_bias_quantile_conformal",
                    bias_point,
                    conformal_quantiles,
                ),
            )
            for variant, point, quantiles in variants:
                prediction_rows.extend(
                    _prediction_rows(
                        fold_id=target_fold_id,
                        variant=variant,
                        seed=seed,
                        config=config,
                        actual=actual,
                        source_raw_point=source_raw,
                        point=point,
                        quantiles=quantiles,
                        fit_fold_count=len(fit_ids),
                        conformal_fold_count=len(conformal_ids),
                    )
                )
                metric_rows.append(
                    _metric_row(
                        fold_id=target_fold_id,
                        variant=variant,
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
                            "fold_id": target_fold_id,
                            "candidate": variant,
                            "seed": seed,
                            "position": config.position_columns[position_index],
                            **row,
                        }
                    )

    if not eligible_fold_ids:
        raise ValueError("no folds are eligible after calibration warmup")
    if not predictions.equals(predictions_original):
        raise RuntimeError("prediction input mutated during calibration")
    if not folds.equals(folds_original):
        raise RuntimeError("fold input mutated during calibration")

    split_df = pd.DataFrame(split_rows)
    parameters_df = pd.DataFrame(parameter_rows)
    predictions_df = pd.DataFrame(prediction_rows)
    metrics_df = pd.DataFrame(metric_rows)
    position_df = pd.DataFrame(position_rows)
    seed_summary = _aggregate_seed_metrics(metrics_df)
    comparison = _comparison(seed_summary)

    report = {
        "schema_version": 1,
        "run_id": config.run_id,
        "status": "PASS",
        "phase": "P8",
        "primary_metric": "Hit@±1",
        "source_candidate": config.source_candidate,
        "source_prediction_sha256": source_prediction_sha256,
        "source_fold_sha256": source_fold_sha256,
        "config_sha256": canonical_sha256(config.model_dump(mode="json")),
        "calibrated_prediction_sha256": canonical_sha256(predictions_df.to_dict(orient="records")),
        "parameter_sha256": canonical_sha256(parameters_df.to_dict(orient="records")),
        "eligible_fold_ids": eligible_fold_ids,
        "warmup_fold_ids": warmup_fold_ids,
        "eligible_fold_count": len(eligible_fold_ids),
        "warmup_fold_count": len(warmup_fold_ids),
        "seed_count": len(seeds),
        "seeds": list(seeds),
        "variants": list(_VARIANTS),
        "bias_fit_scope": "prior_fit_folds_only",
        "quantile_fit_scope": "prior_fit_folds_only",
        "conformal_fit_scope": "later_prior_conformal_folds_only",
        "fit_conformal_target_order": "fit < conformal < target",
        "target_fold_excluded_from_fit": True,
        "future_fold_count_used": 0,
        "holdout_opened": False,
        "prospective_opened": False,
        "best_seed_only_selection": False,
        "automatic_promotion": False,
        "quantile_rearrangement_count": total_rearrangements,
        "conformal_method": "chronological_split_cqr_finite_sample_higher",
        "point_postprocessing": "round_clip_unique_sort_v1",
    }
    return CalibrationResult(
        report=report,
        split_assignments=split_df,
        parameters=parameters_df,
        predictions=predictions_df,
        metrics=metrics_df,
        position_metrics=position_df,
        seed_summary=seed_summary,
        comparison=comparison,
    )
