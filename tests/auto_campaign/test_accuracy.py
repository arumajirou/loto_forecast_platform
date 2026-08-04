from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from loto.auto_campaign.accuracy import (
    AccuracySettings,
    decode_pm1_sequence,
    filter_tasks_by_promotion,
    task_signature,
    wilson_lower_bound,
)
from loto.auto_campaign.tasks import CampaignTask


def test_wilson_lower_bound_is_monotonic() -> None:
    assert wilson_lower_bound(0, 10) == 0.0
    assert wilson_lower_bound(8, 10) < wilson_lower_bound(9, 10)
    assert wilson_lower_bound(9, 10) < wilson_lower_bound(10, 10)


def test_pm1_decoder_returns_strictly_increasing_numbers() -> None:
    settings = AccuracySettings()
    decoded = decode_pm1_sequence(
        np.array([4.2, 10.4, 16.1, 22.2, 28.0]),
        [[-1.0, 0.0, 1.0]] * 5,
        settings,
    )
    assert decoded.shape == (5,)
    assert np.all(np.diff(decoded) > 0)
    assert int(decoded.min()) >= 1
    assert int(decoded.max()) <= 31


def test_promotion_filter_is_signature_based(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    allowed = task_signature("AutoMLP", "u_shared", None)
    (source / "promotion_plan.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "allowed_task_signatures": [allowed],
            }
        ),
        encoding="utf-8",
    )
    tasks = [
        CampaignTask(
            stage="oof",
            model_name="AutoMLP",
            track="u_shared",
            position=None,
            seed=1,
        ),
        CampaignTask(
            stage="oof",
            model_name="AutoTFT",
            track="u_shared",
            position=None,
            seed=1,
        ),
    ]
    filtered = filter_tasks_by_promotion(tasks, source)
    assert len(filtered) == 1
    assert filtered[0].model_name == "AutoMLP"


def test_decoder_can_shift_from_nearest_rounding() -> None:
    settings = AccuracySettings(
        decoder_distance_penalty=0.02,
        decoder_alpha=0.01,
    )
    predictions = np.array([4.0, 10.0, 16.0, 22.0, 28.0])
    residuals = [[2.0, 2.0, 2.0]] * 5
    decoded = decode_pm1_sequence(predictions, residuals, settings)
    assert np.array_equal(decoded, np.array([6.0, 12.0, 18.0, 24.0, 30.0]))


def test_accuracy_settings_reject_unknown_yaml_key(tmp_path: Path) -> None:
    path = tmp_path / "accuracy.yaml"
    path.write_text("unknown_setting: 1\n", encoding="utf-8")
    try:
        AccuracySettings.from_yaml(path)
    except ValueError as exc:
        assert "unknown accuracy settings" in str(exc)
    else:
        raise AssertionError("unknown setting was accepted")
