import numpy as np

from loto.auto_campaign.metrics import nearest_unique_sorted, prediction_variants


def test_reconciliation_is_integer_unique_sorted() -> None:
    values = np.array([8.7, 8.8, 8.9, 20.2, 40.0])
    reconciled = nearest_unique_sorted(values)
    assert np.all(np.diff(reconciled) > 0)
    assert np.all(reconciled == np.rint(reconciled))
    assert reconciled.min() >= 1
    assert reconciled.max() <= 31


def test_prediction_variants_include_reconciled_for_draw() -> None:
    variants = prediction_variants(np.array([1.2, 2.2, 3.2, 4.2, 5.2]))
    assert set(variants) == {"raw", "rounded", "reconciled"}
