from __future__ import annotations

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
