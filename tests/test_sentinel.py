"""Leakage must be falsifiable, not asserted."""
import numpy as np
import pytest

from loto.evaluation.sentinel import (
    audit_feature_causality,
    permutation_sentinel,
    run_sentinel_suite,
    time_shift_sentinel,
)


def _honest_fit(x, y, x_new):
    del x, x_new
    return np.tile(np.median(y, axis=0), (y.shape[0], 1))


def _leaky_fit(x, y, x_new):
    del x, x_new
    return y.copy()  # returns the labels verbatim


def _mae(y_true, y_pred):
    return float(np.abs(np.asarray(y_true) - np.asarray(y_pred)).mean())


def test_permutation_control_passes_for_an_honest_model():
    rng = np.random.default_rng(0)
    y = rng.integers(1, 38, size=(120, 7)).astype(float)
    x = np.arange(120, dtype=float).reshape(-1, 1)
    v = permutation_sentinel(_honest_fit, x, y, _mae, baseline=10.0,
                             higher_is_better=False, tolerance=1.0, n_repeats=5)
    assert not v.tripped


def test_permutation_control_catches_a_leaking_model():
    rng = np.random.default_rng(1)
    y = rng.integers(1, 38, size=(120, 7)).astype(float)
    x = np.arange(120, dtype=float).reshape(-1, 1)
    v = permutation_sentinel(_leaky_fit, x, y, _mae, baseline=10.0,
                             higher_is_better=False, tolerance=1.0, n_repeats=3)
    assert v.tripped and v.observed == pytest.approx(0.0)


def test_time_shift_control_runs_and_reports():
    rng = np.random.default_rng(2)
    y = rng.integers(1, 38, size=(80, 7)).astype(float)
    x = np.arange(80, dtype=float).reshape(-1, 1)
    v = time_shift_sentinel(_leaky_fit, x, y, _mae, baseline=10.0,
                            higher_is_better=False, tolerance=1.0)
    assert v.control == "time_shift" and v.tripped


def test_time_shift_requires_enough_rows():
    with pytest.raises(ValueError, match="shift"):
        time_shift_sentinel(_honest_fit, np.zeros((1, 1)), np.zeros((1, 7)), _mae, baseline=0.0)


def test_causality_audit_is_exact_for_a_causal_builder():
    def causal(values):
        import pandas as pd
        return pd.Series(list(values), dtype=float).shift(1).rolling(3, min_periods=1).mean().to_numpy()

    v = audit_feature_causality(causal, list(range(50)), index=30)
    assert not v.tripped and v.observed == pytest.approx(0.0)


def test_causality_audit_catches_a_centred_window():
    def leaky(values):
        import pandas as pd
        return pd.Series(list(values), dtype=float).rolling(5, min_periods=1, center=True).mean().to_numpy()

    v = audit_feature_causality(leaky, list(range(50)), index=30)
    assert v.tripped and v.observed > 0.0


def test_causality_audit_rejects_out_of_range_index():
    with pytest.raises(IndexError):
        audit_feature_causality(lambda v: np.asarray(v, dtype=float), [1.0, 2.0], index=9)


def test_suite_blocks_promotion_when_any_control_trips():
    rng = np.random.default_rng(4)
    y = rng.integers(1, 38, size=(60, 7)).astype(float)
    x = np.arange(60, dtype=float).reshape(-1, 1)
    bad = permutation_sentinel(_leaky_fit, x, y, _mae, baseline=10.0,
                               higher_is_better=False, tolerance=1.0, n_repeats=2)
    out = run_sentinel_suite([bad])
    assert out["status"] == "SENTINEL_TRIPPED"
    assert out["promotion_allowed"] is False


def test_clean_suite_does_not_overclaim():
    out = run_sentinel_suite([])
    assert out["status"] == "SENTINEL_CLEAN"
    assert "absence of evidence" in out["interpretation"]
