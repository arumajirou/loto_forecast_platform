from __future__ import annotations

import numpy as np
import pytest

from loto.basicts_campaign.contracts import DatasetPayload
from loto.basicts_campaign.dataset import compile_basic_ts_dataset, split_chronologically
from loto.basicts_campaign.metrics import build_baselines, evaluate_predictions
from loto.basicts_campaign.provenance import verify_sha256s, write_artifact_manifest


def _payload() -> DatasetPayload:
    return DatasetPayload.model_validate(
        {
            "game": "numbers3",
            "rows": [
                {"draw_no": index, "values": [index % 10, (index + 1) % 10, (index + 2) % 10]}
                for index in range(1, 9)
            ],
            "validation_size": 2,
            "holdout_size": 2,
        }
    )


def test_split_is_chronological_and_holdout_is_not_materialized(tmp_path) -> None:
    payload = _payload()
    original = payload.model_dump(mode="json")
    split = split_chronologically(payload)
    assert split.train_draw_no == (1, 2, 3, 4)
    assert split.validation_draw_no == (5, 6)
    assert split.holdout_draw_no == (7, 8)

    evidence = compile_basic_ts_dataset(payload, tmp_path / "dataset")
    assert evidence["formal_holdout_materialized"] is False
    assert not (tmp_path / "dataset" / "holdout_data.npy").exists()
    assert payload.model_dump(mode="json") == original


def test_gap_in_draw_sequence_fails_closed() -> None:
    payload = _payload()
    payload.rows[4].draw_no = 9
    with pytest.raises(ValueError, match="chronological|gap-free"):
        split_chronologically(payload)


def test_hit_at_plus_minus_one_metrics() -> None:
    actual = np.asarray([[1, 5, 9], [2, 6, 8]], dtype=float)
    predicted = np.asarray([[2, 7, 9], [1, 6, 10]], dtype=float)
    metrics = evaluate_predictions(actual, predicted)
    assert metrics["hit_at_plus_minus_1"] == pytest.approx(4 / 6)
    assert metrics["all_position_hit_at_plus_minus_1"] == 0.0
    assert metrics["mae"] == pytest.approx(1.0)


def test_baselines_are_deterministic_and_manifest_verifies(tmp_path) -> None:
    train = np.asarray([[1, 2, 3], [2, 2, 4], [3, 5, 4]], dtype=float)
    first = build_baselines(train, 2, seed=7)
    second = build_baselines(train, 2, seed=7)
    assert set(first) == {
        "random",
        "fixed",
        "mean",
        "median",
        "last",
        "frequency",
        "seasonal_naive",
    }
    assert np.array_equal(first["random"], second["random"])

    (tmp_path / "evidence.json").write_text("{}\n", encoding="utf-8")
    write_artifact_manifest(tmp_path)
    assert verify_sha256s(tmp_path)
