from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.chronos2_campaign.evaluation import (
    OOFConfig,
    PredictionBundle,
    build_rolling_folds,
    persist_oof_result,
    run_oof_evaluation,
)


def _history(rows: int = 12) -> pd.DataFrame:
    values: list[dict[str, object]] = []
    for index in range(rows):
        base = 1 + index % 4
        values.append(
            {
                "draw_no": index + 1,
                "draw_date": f"2026-01-{index + 1:02d}",
                "n1": base,
                "n2": base + 4,
                "n3": base + 8,
            }
        )
    return pd.DataFrame(values)


def _config(**overrides) -> OOFConfig:
    payload = {
        "run_id": "oof-test",
        "position_columns": ("n1", "n2", "n3"),
        "candidate_min": 1,
        "candidate_max": 20,
        "min_train_size": 6,
        "horizon": 2,
        "step_size": 2,
        "seeds": (1, 2, 3),
        "fixed_values": (3.0, 7.0, 11.0),
    }
    payload.update(overrides)
    return OOFConfig.model_validate(payload)


def _predictor_calls():
    calls: list[dict[str, object]] = []

    def predictor(
        history: pd.DataFrame,
        *,
        horizon: int,
        seed: int,
        fold_id: str,
    ) -> PredictionBundle:
        calls.append(
            {
                "rows": len(history),
                "max_draw": int(history["draw_no"].max()),
                "horizon": horizon,
                "seed": seed,
                "fold_id": fold_id,
            }
        )
        last = history[["n1", "n2", "n3"]].iloc[-1].to_numpy(dtype=float)
        point = np.repeat(last[:, None], horizon, axis=1)
        return PredictionBundle(
            point=tuple(tuple(row) for row in point),
            quantiles={
                "0.1": tuple(tuple(row) for row in point - 1.0),
                "0.5": tuple(tuple(row) for row in point),
                "0.9": tuple(tuple(row) for row in point + 1.0),
            },
        )

    return calls, predictor


def test_build_rolling_folds_is_chronological() -> None:
    folds = build_rolling_folds(12, _config())
    assert [fold.fold_id for fold in folds] == ["fold-0000", "fold-0001", "fold-0002"]
    assert all(fold.train_end <= fold.validation_start for fold in folds)
    assert folds[-1].validation_end == 12


def test_build_rolling_folds_rejects_short_history() -> None:
    with pytest.raises(ValueError, match="too short"):
        build_rolling_folds(7, _config())


def test_oof_passes_only_training_rows_to_predictor() -> None:
    calls, predictor = _predictor_calls()
    result = run_oof_evaluation(_history(), _config(), predictor)
    assert result.report["status"] == "PASS"
    assert result.report["train_only_fit"] is True
    assert [call["rows"] for call in calls] == [6, 6, 6, 8, 8, 8, 10, 10, 10]
    assert [call["max_draw"] for call in calls] == [6, 6, 6, 8, 8, 8, 10, 10, 10]


def test_oof_keeps_all_seeds_and_required_baselines() -> None:
    _, predictor = _predictor_calls()
    result = run_oof_evaluation(_history(), _config(), predictor)
    candidates = set(result.seed_summary["candidate"])
    assert candidates == {
        "chronos2",
        "random",
        "fixed",
        "mean",
        "median",
        "last",
        "frequency",
        "seasonal_naive",
        "ar1",
    }
    chronos = result.seed_summary.set_index("candidate").loc["chronos2"]
    random = result.seed_summary.set_index("candidate").loc["random"]
    assert chronos["seed_count"] == 3
    assert random["seed_count"] == 3
    assert bool(chronos["best_seed_only_selection"]) is False
    assert chronos["worst_seed_hit_at_1"] <= chronos["seed_hit_at_1_mean"]
    assert chronos["worst_fold_hit_at_1"] <= chronos["hit_at_1_mean"]
    assert result.report["best_seed_only_selection"] is False
    assert len(result.report["prediction_values_sha256"]) == 64
    assert len(result.report["metrics_sha256"]) == 64
    assert len(result.report["evaluation_code_sha256"]) == 64


def test_oof_records_primary_and_probabilistic_metrics() -> None:
    _, predictor = _predictor_calls()
    result = run_oof_evaluation(_history(), _config(), predictor)
    chronos = result.metrics[result.metrics["candidate"] == "chronos2"]
    assert chronos["hit_at_1"].between(0.0, 1.0).all()
    assert chronos["all_position_hit_at_1"].between(0.0, 1.0).all()
    assert chronos["mae"].ge(0.0).all()
    assert chronos["mse"].ge(0.0).all()
    assert chronos["rmse"].ge(0.0).all()
    assert chronos["pinball_loss"].notna().all()
    assert chronos["crps_approx"].notna().all()
    assert np.allclose(chronos["crps_approx"], 2.0 * chronos["pinball_loss"])
    assert chronos["coverage_80"].notna().all()
    assert chronos["quantile_crossing_count"].eq(0.0).all()


def test_oof_position_metrics_cover_every_position() -> None:
    _, predictor = _predictor_calls()
    result = run_oof_evaluation(_history(), _config(), predictor)
    chronos = result.position_metrics[result.position_metrics["candidate"] == "chronos2"]
    assert set(chronos["position"]) == {"n1", "n2", "n3"}
    assert len(chronos) == 3 * 3 * 3


def test_random_baseline_is_reproducible_across_runs() -> None:
    _, predictor = _predictor_calls()
    first = run_oof_evaluation(_history(), _config(), predictor)
    _, predictor = _predictor_calls()
    second = run_oof_evaluation(_history(), _config(), predictor)
    first_random = first.predictions[first.predictions["candidate"] == "random"]
    second_random = second.predictions[second.predictions["candidate"] == "random"]
    pd.testing.assert_frame_equal(
        first_random.reset_index(drop=True),
        second_random.reset_index(drop=True),
    )
    assert first.report["prediction_values_sha256"] == second.report["prediction_values_sha256"]


def test_oof_rejects_prediction_shape_mismatch() -> None:
    def bad_predictor(history, *, horizon, seed, fold_id):
        del history, seed, fold_id
        return PredictionBundle(point=((1.0,) * horizon,))

    with pytest.raises(ValueError, match="prediction shape"):
        run_oof_evaluation(_history(), _config(), bad_predictor)


def test_oof_rejects_quantile_crossing() -> None:
    def bad_predictor(history, *, horizon, seed, fold_id):
        del history, seed, fold_id
        point = ((1.0,) * horizon, (5.0,) * horizon, (9.0,) * horizon)
        return PredictionBundle(
            point=point,
            quantiles={
                "0.1": ((2.0,) * horizon,) * 3,
                "0.9": ((1.0,) * horizon,) * 3,
            },
        )

    with pytest.raises(ValueError, match="quantile crossing"):
        run_oof_evaluation(_history(), _config(), bad_predictor)


def test_oof_source_dataframe_is_not_mutated() -> None:
    history = _history()
    before = history.copy(deep=True)
    _, predictor = _predictor_calls()
    run_oof_evaluation(history, _config(), predictor)
    pd.testing.assert_frame_equal(history, before)


def test_oof_rejects_invalid_sorted_geometry() -> None:
    history = _history()
    history.loc[0, ["n1", "n2", "n3"]] = [9, 5, 1]
    _, predictor = _predictor_calls()
    with pytest.raises(ValueError, match="not ascending"):
        run_oof_evaluation(history, _config(), predictor)


def test_oof_supports_position_ranges() -> None:
    config = _config(
        position_columns=("n1", "n2", "n3"),
        candidate_min=1,
        candidate_max=15,
        position_ranges={"n1": (1, 5), "n2": (6, 10), "n3": (11, 15)},
        fixed_values=(3.0, 8.0, 13.0),
    )
    history = _history()
    history["n1"] = [1 + index % 5 for index in range(len(history))]
    history["n2"] = [6 + index % 5 for index in range(len(history))]
    history["n3"] = [11 + index % 5 for index in range(len(history))]
    _, predictor = _predictor_calls()
    result = run_oof_evaluation(history, config, predictor)
    random_rows = result.predictions[result.predictions["candidate"] == "random"]
    bounds = {"n1": (1, 5), "n2": (6, 10), "n3": (11, 15)}
    for position, group in random_rows.groupby("position"):
        lower, upper = bounds[position]
        assert group["point"].between(lower, upper).all()


def test_persist_oof_result_writes_checksums(tmp_path: Path) -> None:
    _, predictor = _predictor_calls()
    result = run_oof_evaluation(_history(), _config(), predictor)
    output = tmp_path / "oof"
    artifacts = persist_oof_result(result, output)
    assert Path(artifacts["manifest"]).is_file()
    sums = Path(artifacts["sha256sums"]).read_text(encoding="utf-8").splitlines()
    assert sums
    for line in sums:
        digest, relative = line.split("  ", 1)
        path = output / relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert artifacts["report"]["holdout_opened"] is False
    assert artifacts["report"]["prospective_opened"] is False


def test_persist_oof_result_refuses_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "oof"
    output.mkdir()
    (output / "existing.txt").write_text("do not overwrite", encoding="utf-8")
    _, predictor = _predictor_calls()
    result = run_oof_evaluation(_history(), _config(), predictor)
    with pytest.raises(FileExistsError, match="not empty"):
        persist_oof_result(result, output)


def test_oof_config_rejects_overlapping_validation_by_default() -> None:
    with pytest.raises(ValueError, match="step_size"):
        _config(horizon=3, step_size=1)


def test_oof_rejects_gap_in_draw_numbers() -> None:
    history = _history()
    history.loc[7:, "draw_no"] += 1
    _, predictor = _predictor_calls()
    with pytest.raises(ValueError, match="gap-free"):
        run_oof_evaluation(history, _config(), predictor)


def test_oof_rejects_nonmonotonic_dates() -> None:
    history = _history()
    history.loc[7, "draw_date"] = history.loc[5, "draw_date"]
    _, predictor = _predictor_calls()
    with pytest.raises(ValueError, match="draw_date"):
        run_oof_evaluation(history, _config(), predictor)


def test_oof_preserves_raw_and_reconciles_point_predictions() -> None:
    def predictor(history, *, horizon, seed, fold_id):
        del history, seed, fold_id
        raw = (
            (5.2,) * horizon,
            (5.3,) * horizon,
            (5.4,) * horizon,
        )
        return PredictionBundle(point=raw)

    result = run_oof_evaluation(_history(), _config(), predictor)
    rows = result.predictions[result.predictions["candidate"] == "chronos2"]
    assert rows["raw_point"].isin([5.2, 5.3, 5.4]).all()
    for (_, _, _horizon_step), group in rows.groupby(["fold_id", "seed", "horizon_step"]):
        points = group.sort_values("position")["point"].tolist()
        assert points == sorted(points)
        assert len(points) == len(set(points))
        assert all(float(value).is_integer() for value in points)
    assert set(rows["prediction_variant"]) == {"reconciled"}


def test_oof_baseline_comparison_contains_every_baseline() -> None:
    _, predictor = _predictor_calls()
    result = run_oof_evaluation(_history(), _config(), predictor)
    assert set(result.baseline_comparison["baseline"]) == {
        "random",
        "fixed",
        "mean",
        "median",
        "last",
        "frequency",
        "seasonal_naive",
        "ar1",
    }
