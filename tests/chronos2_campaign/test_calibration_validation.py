from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from loto.chronos2_campaign.calibration import (
    CalibrationConfig,
    run_calibration_evaluation,
)
from loto.chronos2_campaign.calibration_methods import (
    bias_offset,
    finite_sample_conformal_quantile,
    quantile_residual_correction,
    rearrange_quantiles,
)

LEVELS = (0.05, 0.1, 0.5, 0.9, 0.95)


def _config(**updates: object) -> CalibrationConfig:
    values: dict[str, object] = {
        "run_id": "chronos2-p8-test",
        "position_columns": ("n1", "n2"),
        "horizon": 1,
        "candidate_min": 0,
        "candidate_max": 20,
        "allow_duplicates": True,
        "sort_policy": "preserve",
        "min_fit_folds": 2,
        "min_conformal_folds": 2,
        "conformal_fraction": 0.4,
        "interval_coverages": (0.8, 0.9),
        "quantile_levels": LEVELS,
    }
    values.update(updates)
    return CalibrationConfig.model_validate(values)


def _inputs(
    *,
    fold_count: int = 9,
    seeds: tuple[int, ...] = (1, 2),
    horizon: int = 1,
    bias: float = 3.0,
    crossing: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    for fold_index in range(fold_count):
        fold_id = f"fold-{fold_index:04d}"
        fold_rows.append(
            {
                "fold_id": fold_id,
                "train_end_exclusive": fold_index + 5,
                "validation_start": fold_index + 5,
                "validation_end_exclusive": fold_index + 5 + horizon,
                "chronology_verified": True,
            }
        )
        for seed in seeds:
            for position_index, position in enumerate(("n1", "n2")):
                for horizon_step in range(1, horizon + 1):
                    actual = float(4 + position_index * 5 + fold_index % 3 + horizon_step - 1)
                    raw_point = actual + bias + 0.1 * (seed - 1)
                    point = float(round(raw_point))
                    quantiles = {
                        0.05: raw_point - 0.8,
                        0.1: raw_point - 0.5,
                        0.5: raw_point,
                        0.9: raw_point + 0.5,
                        0.95: raw_point + 0.8,
                    }
                    if crossing and fold_index == fold_count - 1:
                        quantiles[0.5] = raw_point + 2.0
                        quantiles[0.9] = raw_point + 1.0
                    prediction_rows.append(
                        {
                            "fold_id": fold_id,
                            "candidate": "chronos2",
                            "seed": seed,
                            "position": position,
                            "horizon_step": horizon_step,
                            "actual": actual,
                            "raw_point": raw_point,
                            "point": point,
                            **{f"q_{level}": value for level, value in quantiles.items()},
                        }
                    )
        # P7 output also contains baselines; P8 must ignore them rather than fit on them.
        prediction_rows.append(
            {
                "fold_id": fold_id,
                "candidate": "mean",
                "seed": np.nan,
                "position": "n1",
                "horizon_step": 1,
                "actual": 1.0,
                "raw_point": 1.0,
                "point": 1.0,
                **{f"q_{level}": 1.0 for level in LEVELS},
            }
        )
    return pd.DataFrame(prediction_rows), pd.DataFrame(fold_rows)


def _verify_sha256sums(root: Path) -> None:
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        assert actual == expected


def test_source_hashes_are_stable() -> None:
    predictions, folds = _inputs()
    first = run_calibration_evaluation(predictions, folds, _config()).report
    second = run_calibration_evaluation(predictions, folds, _config()).report
    assert first["source_prediction_sha256"] == second["source_prediction_sha256"]
    assert first["source_fold_sha256"] == second["source_fold_sha256"]
    assert first["parameter_sha256"] == second["parameter_sha256"]


def test_config_rejects_duplicate_positions() -> None:
    with pytest.raises(ValidationError, match="position_columns must be unique"):
        _config(position_columns=("n1", "n1"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("interval_coverages", ()),
        ("interval_coverages", (0.8, 0.8)),
        ("interval_coverages", (1.0,)),
        ("quantile_levels", ()),
        ("quantile_levels", (0.1, 0.1, 0.5, 0.9)),
        ("quantile_levels", (0.0, 0.5, 1.0)),
        ("sort_policy", "invalid"),
        ("bias_statistic", "mode"),
        ("quantile_correction_method", "nearest"),
        ("conformal_quantile_method", "linear"),
    ],
)
def test_config_rejects_invalid_policy_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _config(**{field: value})


def test_position_ranges_are_validated() -> None:
    with pytest.raises(ValidationError, match="exactly cover"):
        _config(position_ranges={"n1": (0, 10)})
    with pytest.raises(ValidationError, match="outside candidate domain"):
        _config(position_ranges={"n1": (-1, 10), "n2": (0, 20)})


def test_method_helpers_fail_closed_on_invalid_vectors() -> None:
    with pytest.raises(ValueError, match="bias residuals"):
        bias_offset([], "mean")
    with pytest.raises(ValueError, match="unsupported bias"):
        bias_offset([1.0], "mode")
    with pytest.raises(ValueError, match="quantile residuals"):
        quantile_residual_correction([np.nan], 0.5, "linear")
    with pytest.raises(ValueError, match="conformal scores"):
        finite_sample_conformal_quantile([], coverage=0.9)
    with pytest.raises(ValueError, match="non-negative"):
        finite_sample_conformal_quantile([-1.0], coverage=0.9)
    with pytest.raises(ValueError, match="quantile values"):
        rearrange_quantiles({0.5: np.nan})


def test_missing_fold_columns_fail_closed() -> None:
    predictions, folds = _inputs()
    with pytest.raises(ValueError, match="fold input is missing columns"):
        run_calibration_evaluation(
            predictions,
            folds.drop(columns=["train_end_exclusive"]),
            _config(),
        )


def test_source_candidate_and_seed_validation() -> None:
    predictions, folds = _inputs()
    with pytest.raises(ValueError, match="source candidate not found"):
        run_calibration_evaluation(predictions, folds, _config(source_candidate="missing"))
    selected_index = predictions.query("candidate == 'chronos2'").index[0]
    predictions.loc[selected_index, "seed"] = np.nan
    with pytest.raises(ValueError, match="explicit seed"):
        run_calibration_evaluation(predictions, folds, _config())


def test_fractional_seed_is_rejected() -> None:
    predictions, folds = _inputs()
    selected_index = predictions.query("candidate == 'chronos2'").index[0]
    predictions.loc[selected_index, "seed"] = 1.5
    with pytest.raises(ValueError, match="seed values must be integers"):
        run_calibration_evaluation(predictions, folds, _config())


def test_fold_chronology_flag_parses_strings_and_rejects_false() -> None:
    predictions, folds = _inputs()
    folds["chronology_verified"] = "true"
    run_calibration_evaluation(predictions, folds, _config())
    folds.loc[0, "chronology_verified"] = "false"
    with pytest.raises(ValueError, match="chronology_verified=true"):
        run_calibration_evaluation(predictions, folds, _config())
    folds.loc[0, "chronology_verified"] = "unknown"
    with pytest.raises(ValueError, match="invalid chronology_verified"):
        run_calibration_evaluation(predictions, folds, _config())


def test_fold_boundaries_are_validated() -> None:
    predictions, folds = _inputs()
    folds.loc[0, "train_end_exclusive"] = folds.loc[0, "validation_start"] + 1
    with pytest.raises(ValueError, match="train_end_exclusive"):
        run_calibration_evaluation(predictions, folds, _config())
    predictions, folds = _inputs()
    folds.loc[0, "validation_end_exclusive"] = folds.loc[0, "validation_start"]
    with pytest.raises(ValueError, match="validation_end_exclusive"):
        run_calibration_evaluation(predictions, folds, _config())


def test_position_and_horizon_mismatch_fail_closed() -> None:
    predictions, folds = _inputs()
    selected = predictions["candidate"] == "chronos2"
    predictions.loc[selected & (predictions["position"] == "n2"), "position"] = "n3"
    with pytest.raises(ValueError, match="positions do not match"):
        run_calibration_evaluation(predictions, folds, _config())
    predictions, folds = _inputs()
    predictions.loc[predictions["candidate"] == "chronos2", "horizon_step"] = 2
    with pytest.raises(ValueError, match="horizon steps"):
        run_calibration_evaluation(predictions, folds, _config())


def test_nonfinite_source_value_fails_closed() -> None:
    predictions, folds = _inputs()
    selected_index = predictions.query("candidate == 'chronos2'").index[0]
    predictions.loc[selected_index, "raw_point"] = np.inf
    with pytest.raises(ValueError, match="non-finite"):
        run_calibration_evaluation(predictions, folds, _config())


def test_no_eligible_fold_fails_closed() -> None:
    predictions, folds = _inputs(fold_count=4)
    with pytest.raises(ValueError, match="no folds are eligible"):
        run_calibration_evaluation(predictions, folds, _config())
