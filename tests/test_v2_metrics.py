import numpy as np

from loto.evaluation.detailed_metrics import detailed_draw_metrics
from loto.evaluation.splits import rolling_folds


def test_detailed_within_one_metrics():
    actual = np.array([[1, 5, 10, 15, 20, 30, 37]])
    predicted = np.array([[2, 5, 9, 16, 22, 29, 37]])
    out = detailed_draw_metrics(actual, predicted)
    assert out["mean_within_1"] == 6 / 7
    assert out["all_positions_within_1"] == 0.0
    assert out["position_5_within_1"] == 0.0


def test_rolling_folds_do_not_overlap_future():
    folds = rolling_folds(200, folds=3, test_size=10, min_train_size=100, gap=2)
    assert len(folds) == 3
    assert all(f.train_end + 2 == f.test_start for f in folds)
