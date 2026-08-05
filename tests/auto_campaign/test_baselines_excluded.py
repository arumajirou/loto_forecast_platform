from __future__ import annotations

import inspect

from loto.auto_campaign import runner


def test_baseline_execution_is_not_part_of_campaign() -> None:
    source = inspect.getsource(runner)

    forbidden = [
        "evaluate_baselines(",
        "baseline_predictions.parquet",
        "baseline_metrics.parquet",
        "ALL_MODEL_BASELINE_COMPARISON",
    ]

    for value in forbidden:
        assert value not in source


def test_manifest_declares_auto_model_only_scope() -> None:
    source = inspect.getsource(runner)

    assert '"baseline_models_included": False' in source
    assert '"baseline_execution_enabled": False' in source
    assert '"ranking_scope": "auto_models_only"' in source
