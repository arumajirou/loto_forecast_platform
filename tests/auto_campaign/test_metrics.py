import numpy as np

from loto.auto_campaign.metrics import score_draw_matrix


def test_hit_pm1_is_primary_metric() -> None:
    actual = np.array([[1, 5, 10, 15, 20]], dtype=float)
    predicted = np.array([[2, 4, 12, 15, 19]], dtype=float)
    metrics = score_draw_matrix(actual, predicted)
    assert metrics["hit_pm1"] == 0.8
    assert metrics["all_positions_hit_pm1"] == 0.0
