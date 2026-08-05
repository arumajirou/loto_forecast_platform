from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("pyarrow")

from loto.auto_campaign.evaluation import summarize_metrics


def test_oof_summary_records_worst_seed_and_fold(tmp_path: Path) -> None:
    task_root = tmp_path / "tasks" / "one"
    task_root.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "variant": "rounded",
                "hit_pm1": 1.0,
                "all_positions_hit_pm1": 1.0,
                "exact_hit": 0.0,
                "mae": 0.5,
                "mse": 0.25,
                "rmse": 0.5,
            }
        ]
    ).to_parquet(task_root / "metrics_by_variant.parquet", index=False)
    (task_root / "manifest.json").write_text(
        """{
          "task": {
            "stage": "oof",
            "model_name": "AutoMLP",
            "track": "u_shared",
            "position": null,
            "seed": 1,
            "fold": 1,
            "origin": 100,
            "backend": "ray",
            "config_index": null
          }
        }""",
        encoding="utf-8",
    )

    summary = summarize_metrics(tmp_path)

    assert summary["fold_count"] == 1
    result = pd.read_parquet(tmp_path / "seed_metric_summary.parquet")
    assert result.loc[0, "worst_seed_hit_pm1"] == 1.0
    assert result.loc[0, "worst_fold_hit_pm1"] == 1.0


def test_local_combined_metrics_preserve_config_index(tmp_path: Path) -> None:
    actual = [1.0, 5.0, 10.0, 15.0, 20.0]
    predictions_by_config = {
        0: actual,
        1: [11.0, 15.0, 20.0, 25.0, 30.0],
    }

    for config_index, predictions in predictions_by_config.items():
        for position, (actual_value, prediction) in enumerate(
            zip(actual, predictions, strict=True),
            start=1,
        ):
            task_root = tmp_path / "tasks" / f"config-{config_index}" / f"position-{position}"
            task_root.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "variant": "raw",
                        "unique_id": f"P{position}",
                        "actual": actual_value,
                        "prediction": prediction,
                    }
                ]
            ).to_parquet(task_root / "prediction_records.parquet", index=False)
            (task_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "task": {
                            "stage": "validation_replay",
                            "model_name": "AutoMLP",
                            "track": "u_local",
                            "position": f"P{position}",
                            "seed": 1,
                            "fold": 1,
                            "origin": 100,
                            "backend": "ray",
                            "config_index": config_index,
                        }
                    }
                ),
                encoding="utf-8",
            )

    summary = summarize_metrics(tmp_path)

    assert summary["local_combined_rows"] == 6
    combined = pd.read_parquet(tmp_path / "evaluation_metrics.parquet")
    raw = combined[
        combined["track"].eq("u_local_combined") & combined["variant"].eq("raw")
    ].sort_values("config_index")

    assert raw["config_index"].tolist() == [0, 1]
    assert raw["hit_pm1"].tolist() == [1.0, 0.0]
    assert raw["all_positions_hit_pm1"].tolist() == [1.0, 0.0]

    summary_specs = [
        ("per_seed_metrics.parquet", "hit_pm1", "all_positions_hit_pm1"),
        ("per_fold_metrics.parquet", "hit_pm1", "all_positions_hit_pm1"),
        ("seed_metric_summary.parquet", "hit_pm1_mean", "all_positions_hit_pm1_mean"),
        ("model_ranking.parquet", "hit_pm1_mean", "all_positions_hit_pm1_mean"),
    ]
    for filename, hit_column, all_positions_column in summary_specs:
        summary_frame = pd.read_parquet(tmp_path / filename)
        local_raw = summary_frame[
            summary_frame["track"].eq("u_local_combined")
            & summary_frame["variant"].eq("raw")
        ].sort_values("config_index")

        assert local_raw["config_index"].tolist() == [0, 1]
        assert local_raw[hit_column].tolist() == [1.0, 0.0]
        assert local_raw[all_positions_column].tolist() == [1.0, 0.0]


def test_summary_preserves_stage_backend_and_config_identity(tmp_path: Path) -> None:
    candidates = [
        ("ray", 0, 1.0),
        ("ray", 1, 0.5),
        ("optuna", 0, 0.0),
    ]
    for index, (backend, config_index, hit_pm1) in enumerate(candidates):
        task_root = tmp_path / "tasks" / f"candidate-{index}"
        task_root.mkdir(parents=True)
        error = 1.0 - hit_pm1
        pd.DataFrame(
            [
                {
                    "variant": "rounded",
                    "hit_pm1": hit_pm1,
                    "all_positions_hit_pm1": hit_pm1,
                    "exact_hit": hit_pm1,
                    "mae": error,
                    "mse": error**2,
                    "rmse": error,
                }
            ]
        ).to_parquet(task_root / "metrics_by_variant.parquet", index=False)
        (task_root / "manifest.json").write_text(
            json.dumps(
                {
                    "task": {
                        "stage": "oof",
                        "model_name": "AutoMLP",
                        "track": "u_shared",
                        "position": None,
                        "seed": 1,
                        "fold": 1,
                        "origin": 100 + index,
                        "backend": backend,
                        "config_index": config_index,
                    }
                }
            ),
            encoding="utf-8",
        )

    summarize_metrics(tmp_path)

    summary_specs = [
        ("per_seed_metrics.parquet", "hit_pm1"),
        ("per_fold_metrics.parquet", "hit_pm1"),
        ("seed_metric_summary.parquet", "hit_pm1_mean"),
        ("model_ranking.parquet", "hit_pm1_mean"),
    ]
    expected_identity = [("optuna", 0), ("ray", 0), ("ray", 1)]
    expected_hit_pm1 = [0.0, 1.0, 0.5]

    for filename, hit_column in summary_specs:
        frame = pd.read_parquet(tmp_path / filename).sort_values(
            ["backend", "config_index"],
            kind="stable",
        )
        identity = list(
            zip(
                frame["backend"],
                frame["config_index"],
                strict=True,
            )
        )
        assert frame["stage"].tolist() == ["oof", "oof", "oof"]
        assert identity == expected_identity
        assert frame[hit_column].tolist() == expected_hit_pm1
