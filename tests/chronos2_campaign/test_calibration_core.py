from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from loto.chronos2_campaign.calibration import (
    CalibrationConfig,
    persist_calibration_result,
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


def test_config_requires_interval_quantiles() -> None:
    with pytest.raises(ValidationError, match="interval endpoints"):
        _config(quantile_levels=(0.1, 0.5, 0.9))


def test_config_rejects_invalid_conformal_fraction() -> None:
    with pytest.raises(ValidationError):
        _config(conformal_fraction=1.0)


def test_bias_offset_supports_mean_and_median() -> None:
    assert bias_offset([1.0, 2.0, 9.0], "mean") == pytest.approx(4.0)
    assert bias_offset([1.0, 2.0, 9.0], "median") == pytest.approx(2.0)


def test_quantile_residual_correction_is_deterministic() -> None:
    value = quantile_residual_correction([-3.0, -2.0, -1.0], 0.5, "linear")
    assert value == pytest.approx(-2.0)


def test_finite_sample_conformal_quantile_is_conservative() -> None:
    assert finite_sample_conformal_quantile([0.0, 1.0, 2.0, 3.0], coverage=0.9) == 3.0


def test_rearrange_quantiles_removes_crossing() -> None:
    result, changed = rearrange_quantiles({0.1: 1.0, 0.5: 3.0, 0.9: 2.0})
    assert list(result.values()) == [1.0, 3.0, 3.0]
    assert changed == 1


def test_calibration_uses_only_prior_folds() -> None:
    predictions, folds = _inputs()
    result = run_calibration_evaluation(predictions, folds, _config())
    evaluated = result.split_assignments.query("status == 'EVALUATED'")
    assert not evaluated.empty
    for row in evaluated.to_dict(orient="records"):
        fit_ids = json.loads(row["fit_fold_ids"])
        conformal_ids = json.loads(row["conformal_fold_ids"])
        target = row["target_fold_id"]
        assert target not in fit_ids
        assert target not in conformal_ids
        assert row["future_fold_count_used"] == 0
        assert row["chronology_verified"]


def test_warmup_folds_are_not_scored_for_any_variant() -> None:
    predictions, folds = _inputs()
    result = run_calibration_evaluation(predictions, folds, _config())
    warmup = set(result.report["warmup_fold_ids"])
    assert warmup
    assert warmup.isdisjoint(set(result.predictions["fold_id"]))
    counts = result.metrics.groupby("candidate")["fold_id"].nunique()
    assert counts.nunique() == 1


def test_bias_calibration_improves_systematic_offset() -> None:
    predictions, folds = _inputs(bias=3.0)
    result = run_calibration_evaluation(predictions, folds, _config())
    summary = result.seed_summary.set_index("candidate")
    raw = summary.loc["chronos2_uncalibrated"]
    calibrated = summary.loc["chronos2_bias_calibrated"]
    assert calibrated["hit_at_1_mean"] > raw["hit_at_1_mean"]
    assert calibrated["mae_mean"] < raw["mae_mean"]


def test_all_seeds_are_retained() -> None:
    predictions, folds = _inputs(seeds=(1, 2, 7))
    result = run_calibration_evaluation(predictions, folds, _config())
    assert set(result.predictions["seed"]) == {1, 2, 7}
    assert set(result.seed_summary["seed_count"]) == {3}
    assert not result.report["best_seed_only_selection"]


def test_quantile_and_conformal_variants_are_emitted() -> None:
    predictions, folds = _inputs()
    result = run_calibration_evaluation(predictions, folds, _config())
    assert set(result.predictions["candidate"]) == {
        "chronos2_uncalibrated",
        "chronos2_bias_calibrated",
        "chronos2_bias_quantile_calibrated",
        "chronos2_bias_quantile_conformal",
    }
    conformal = result.predictions.query("candidate == 'chronos2_bias_quantile_conformal'")
    assert conformal["q_0.05"].notna().all()
    assert conformal["q_0.95"].notna().all()


def test_conformal_intervals_are_not_narrower_than_quantile_intervals() -> None:
    predictions, folds = _inputs()
    result = run_calibration_evaluation(predictions, folds, _config())
    quantile = result.predictions.query(
        "candidate == 'chronos2_bias_quantile_calibrated'"
    ).reset_index(drop=True)
    conformal = result.predictions.query(
        "candidate == 'chronos2_bias_quantile_conformal'"
    ).reset_index(drop=True)
    assert (
        (conformal["q_0.95"] - conformal["q_0.05"]) >= (quantile["q_0.95"] - quantile["q_0.05"])
    ).all()


def test_parameters_preserve_fit_and_conformal_hashes() -> None:
    predictions, folds = _inputs()
    result = run_calibration_evaluation(predictions, folds, _config())
    assert result.parameters["fit_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert result.parameters["conformal_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert result.parameters["target_fold_excluded"].all()
    assert (result.parameters["future_fold_count_used"] == 0).all()


def test_missing_required_quantile_column_fails_closed() -> None:
    predictions, folds = _inputs()
    predictions = predictions.drop(columns=["q_0.05"])
    with pytest.raises(ValueError, match="missing columns"):
        run_calibration_evaluation(predictions, folds, _config())


def test_duplicate_source_rows_fail_closed() -> None:
    predictions, folds = _inputs()
    predictions = pd.concat([predictions, predictions.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        run_calibration_evaluation(predictions, folds, _config())


def test_actual_mismatch_across_seeds_fails_closed() -> None:
    predictions, folds = _inputs()
    mask = (
        (predictions["candidate"] == "chronos2")
        & (predictions["fold_id"] == "fold-0000")
        & (predictions["seed"] == 2)
        & (predictions["position"] == "n1")
    )
    predictions.loc[mask, "actual"] += 1.0
    with pytest.raises(ValueError, match="actual values differ"):
        run_calibration_evaluation(predictions, folds, _config())


def test_holdout_rows_are_rejected() -> None:
    predictions, folds = _inputs()
    predictions["split"] = "oof"
    predictions.loc[predictions.index[0], "split"] = "holdout"
    with pytest.raises(ValueError, match="Holdout or Prospective"):
        run_calibration_evaluation(predictions, folds, _config())


def test_non_chronological_fold_metadata_is_rejected() -> None:
    predictions, folds = _inputs()
    folds.loc[1, "validation_start"] = folds.loc[0, "validation_start"]
    with pytest.raises(ValueError, match="strictly increasing"):
        run_calibration_evaluation(predictions, folds, _config())


def test_incomplete_source_grid_is_rejected() -> None:
    predictions, folds = _inputs()
    predictions = predictions.drop(index=predictions.query("candidate == 'chronos2'").index[0])
    with pytest.raises(ValueError, match="grid is incomplete"):
        run_calibration_evaluation(predictions, folds, _config())


def test_inputs_are_not_mutated() -> None:
    predictions, folds = _inputs()
    predictions_before = predictions.copy(deep=True)
    folds_before = folds.copy(deep=True)
    run_calibration_evaluation(predictions, folds, _config())
    pd.testing.assert_frame_equal(predictions, predictions_before)
    pd.testing.assert_frame_equal(folds, folds_before)


def test_report_closes_holdout_prospective_and_promotion() -> None:
    predictions, folds = _inputs()
    report = run_calibration_evaluation(predictions, folds, _config()).report
    assert report["phase"] == "P8"
    assert not report["holdout_opened"]
    assert not report["prospective_opened"]
    assert not report["automatic_promotion"]
    assert report["target_fold_excluded_from_fit"]
    assert report["future_fold_count_used"] == 0


def test_multi_horizon_calibration() -> None:
    predictions, folds = _inputs(horizon=2)
    result = run_calibration_evaluation(predictions, folds, _config(horizon=2))
    assert set(result.predictions["horizon_step"]) == {1, 2}
    assert set(result.parameters["horizon_step"]) == {1, 2}


def test_persist_calibration_result_is_atomic_and_hash_verified(tmp_path: Path) -> None:
    predictions, folds = _inputs()
    result = run_calibration_evaluation(predictions, folds, _config())
    output = tmp_path / "calibration"
    payload = persist_calibration_result(result, output)
    assert Path(payload["manifest"]).is_file()
    assert Path(payload["sha256sums"]).is_file()
    _verify_sha256sums(output)
    manifest = json.loads((output / "ARTIFACT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["phase"] == "P8"
    assert not manifest["holdout_opened"]
    assert not manifest["prospective_opened"]


def test_persist_rejects_nonempty_output(tmp_path: Path) -> None:
    predictions, folds = _inputs()
    result = run_calibration_evaluation(predictions, folds, _config())
    output = tmp_path / "calibration"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        persist_calibration_result(result, output)
    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_comparison_disables_automatic_promotion() -> None:
    predictions, folds = _inputs()
    comparison = run_calibration_evaluation(predictions, folds, _config()).comparison
    assert not comparison["automatic_promotion"].any()
    assert "delta_hit_at_1" in comparison.columns
