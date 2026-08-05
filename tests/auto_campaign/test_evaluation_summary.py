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
            task_root = (
                tmp_path
                / "tasks"
                / f"config-{config_index}"
                / f"position-{position}"
            )
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
