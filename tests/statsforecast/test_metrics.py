import numpy as np
import pandas as pd
import pytest

from loto.statsforecast.metrics import baseline_prediction, evaluate_prediction_frame


def test_hit_at_pm1_and_all_position_hit() -> None:
    frame = pd.DataFrame(
        {
            "unique_id": ["d1", "d2", "d1", "d2"],
            "ds": [1, 1, 2, 2],
            "actual": [1, 8, 3, 7],
            "prediction": [2, 7, 5, 7],
        }
    )
    result = evaluate_prediction_frame(frame)
    assert result["hit_at_pm1"] == 0.75
    assert result["all_position_hit_at_pm1"] == 0.5
    assert set(result["position_metrics"]) == {"d1", "d2"}


def test_frequency_baseline_is_deterministic_on_ties() -> None:
    prediction = baseline_prediction(
        np.array([3, 4, 3, 4], dtype=float),
        horizon=3,
        strategy="frequency",
    )
    np.testing.assert_array_equal(prediction, np.array([3.0, 3.0, 3.0]))


def test_unknown_baseline_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        baseline_prediction(np.array([1.0]), horizon=1, strategy="magic")
