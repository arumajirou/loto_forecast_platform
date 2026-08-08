from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .calibration_contracts import CalibrationConfig
from .evaluation_contracts import OOFConfig


def _quantile_column(level: float) -> str:
    return f"q_{level}"


def _geometry_config(config: CalibrationConfig) -> OOFConfig:
    return OOFConfig(
        run_id=f"{config.run_id}-geometry",
        position_columns=config.position_columns,
        candidate_min=config.candidate_min,
        candidate_max=config.candidate_max,
        allow_duplicates=config.allow_duplicates,
        sort_policy=config.sort_policy,
        position_ranges=config.position_ranges,
        min_train_size=2,
        horizon=config.horizon,
        step_size=config.horizon,
        quantile_levels=config.quantile_levels,
    )


def _validate_inputs(
    predictions: pd.DataFrame,
    folds: pd.DataFrame,
    config: CalibrationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...], tuple[int, ...]]:
    required_predictions = {
        "fold_id",
        "candidate",
        "seed",
        "position",
        "horizon_step",
        "actual",
        "raw_point",
        "point",
    }
    required_predictions.update(_quantile_column(level) for level in config.quantile_levels)
    missing_predictions = sorted(required_predictions - set(predictions.columns))
    if missing_predictions:
        raise ValueError(f"prediction input is missing columns: {missing_predictions}")

    required_folds = {
        "fold_id",
        "train_end_exclusive",
        "validation_start",
        "validation_end_exclusive",
        "chronology_verified",
    }
    missing_folds = sorted(required_folds - set(folds.columns))
    if missing_folds:
        raise ValueError(f"fold input is missing columns: {missing_folds}")

    if "split" in predictions.columns:
        forbidden = {"holdout", "prospective"}
        observed = {str(value).lower() for value in predictions["split"].dropna().unique()}
        if observed & forbidden:
            raise ValueError("Holdout or Prospective rows are forbidden in P8 calibration")

    selected = predictions.loc[predictions["candidate"] == config.source_candidate].copy()
    if selected.empty:
        raise ValueError(f"source candidate not found: {config.source_candidate}")
    if selected["seed"].isna().any():
        raise ValueError("source candidate rows require an explicit seed")
    numeric_seeds = pd.to_numeric(selected["seed"], errors="raise")
    if not np.all(np.equal(numeric_seeds, np.floor(numeric_seeds))):
        raise ValueError("seed values must be integers")
    selected["seed"] = numeric_seeds.astype(int)

    fold_table = folds.copy()
    if fold_table["fold_id"].duplicated().any():
        raise ValueError("fold_id values must be unique")

    def parse_verified(value: object) -> bool:
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        normalized = str(value).strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise ValueError(f"invalid chronology_verified value: {value!r}")

    verified = fold_table["chronology_verified"].map(parse_verified)
    if not verified.all():
        raise ValueError("every fold must have chronology_verified=true")
    fold_table["chronology_verified"] = verified
    fold_table = fold_table.sort_values("validation_start", kind="stable").reset_index(drop=True)
    train_ends = pd.to_numeric(fold_table["train_end_exclusive"], errors="raise").to_numpy()
    starts = pd.to_numeric(fold_table["validation_start"], errors="raise").to_numpy()
    ends = pd.to_numeric(fold_table["validation_end_exclusive"], errors="raise").to_numpy()
    if len(starts) > 1 and not np.all(np.diff(starts) > 0):
        raise ValueError("validation_start values must be strictly increasing")
    if not np.all(train_ends <= starts):
        raise ValueError("fold train_end_exclusive must be <= validation_start")
    if not np.all(ends > starts):
        raise ValueError("fold validation_end_exclusive must be > validation_start")
    fold_ids = tuple(str(value) for value in fold_table["fold_id"])
    if not set(selected["fold_id"]).issubset(set(fold_ids)):
        raise ValueError("prediction rows contain fold_id values absent from fold metadata")

    expected_positions = set(config.position_columns)
    if set(selected["position"]) != expected_positions:
        raise ValueError("prediction positions do not match calibration position_columns")
    expected_horizons = set(range(1, config.horizon + 1))
    observed_horizons = set(pd.to_numeric(selected["horizon_step"], errors="raise").astype(int))
    if observed_horizons != expected_horizons:
        raise ValueError("prediction horizon steps do not match calibration horizon")

    key_columns = ["fold_id", "seed", "position", "horizon_step"]
    if selected.duplicated(key_columns).any():
        raise ValueError("source candidate contains duplicate fold/seed/position/horizon rows")
    seeds = tuple(sorted(int(value) for value in selected["seed"].unique()))
    expected_rows = len(fold_ids) * len(seeds) * len(config.position_columns) * config.horizon
    if len(selected) != expected_rows:
        raise ValueError(
            f"source candidate grid is incomplete: rows={len(selected)}, expected={expected_rows}"
        )

    consistency = selected.groupby(["fold_id", "position", "horizon_step"])["actual"]
    if (consistency.nunique(dropna=False) != 1).any():
        raise ValueError("actual values differ across seeds for the same target cell")

    numeric_columns = ["actual", "raw_point", "point"] + [
        _quantile_column(level) for level in config.quantile_levels
    ]
    for column in numeric_columns:
        values = pd.to_numeric(selected[column], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"column {column} contains non-finite values")
        selected[column] = values

    selected["horizon_step"] = pd.to_numeric(selected["horizon_step"], errors="raise").astype(int)
    selected["fold_id"] = selected["fold_id"].astype(str)
    return selected, fold_table, fold_ids, seeds


def _split_prior_folds(
    prior_fold_ids: Sequence[str],
    config: CalibrationConfig,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    required = config.min_fit_folds + config.min_conformal_folds
    if len(prior_fold_ids) < required:
        return None
    desired_fit = int(np.floor(len(prior_fold_ids) * (1.0 - config.conformal_fraction)))
    fit_count = max(config.min_fit_folds, desired_fit)
    fit_count = min(fit_count, len(prior_fold_ids) - config.min_conformal_folds)
    fit_ids = tuple(prior_fold_ids[:fit_count])
    conformal_ids = tuple(prior_fold_ids[fit_count:])
    if len(fit_ids) < config.min_fit_folds:
        raise RuntimeError("internal split produced too few fit folds")
    if len(conformal_ids) < config.min_conformal_folds:
        raise RuntimeError("internal split produced too few conformal folds")
    return fit_ids, conformal_ids
