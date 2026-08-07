from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from loto.darts_campaign.evaluation import evaluate_predictions, generate_baselines
from loto.darts_campaign.protocol import DartsRequest, EvaluationPolicy, GameGeometry


def test_metrics_and_seeded_baselines(tmp_path) -> None:
    actual = np.asarray([[1, 2], [10, 10]], dtype=float)
    predicted = np.asarray([[2, 4], [9, 10]], dtype=float)
    result = evaluate_predictions(actual, predicted)
    assert result["hit_at_plus_minus_1"] == 0.75
    assert result["position_hit_at_plus_minus_1"] == [0.5, 1.0]
    assert result["all_position_hit_at_plus_minus_1"] == 0.5

    frame = pd.DataFrame({"draw_no": [1, 2, 3], "n1": [1, 2, 2], "n2": [8, 9, 9]})
    geometry = GameGeometry(game_id="numbers2", positions=2, min_value=0, max_value=9)
    policy = EvaluationPolicy(enabled=True, holdout_size=2, season_length=2)
    first = generate_baselines(frame, geometry, policy, seed=1)
    second = generate_baselines(frame, geometry, policy, seed=1)
    for name in first:
        np.testing.assert_array_equal(first[name], second[name])


def test_protocol_rejects_invalid_evaluation_and_persistence(tmp_path) -> None:
    base = {
        "run_id": "run-1",
        "mode": "fit_predict",
        "geometry": {"game_id": "numbers2", "positions": 2, "min_value": 0, "max_value": 9},
        "model": {"public_name": "NaiveDrift"},
        "horizon": 2,
        "artifact_dir": tmp_path,
    }
    with pytest.raises(ValidationError):
        DartsRequest.model_validate(base | {"evaluation": {"enabled": True, "holdout_size": 1}})
    with pytest.raises(ValidationError):
        DartsRequest.model_validate(base | {"persistence": {"verify_save_load": True}})
