"""Calibration layer. Shipped at 0% coverage in v2.1.0 and reachable from nowhere.

Constitution: every component must justify itself. These tests establish what the two
calibrators actually guarantee, so a future decision to keep or delete them is informed.
"""

import numpy as np

from loto.calibration.calibrators import PlattCalibrator, TemperatureScaler
from loto.evaluation.metrics_general import expected_calibration_error


def _miscalibrated(n=800, seed=0):
    """Probabilities that are systematically over-confident."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < true_p).astype(int)
    logit = np.log(true_p / (1 - true_p))
    over = 1.0 / (1.0 + np.exp(-2.5 * logit))  # sharpened => over-confident
    return over, y


def test_platt_reduces_calibration_error():
    p, y = _miscalibrated()
    before = expected_calibration_error(y, p)
    after = expected_calibration_error(y, PlattCalibrator().fit(p, y).transform(p))
    assert after < before


def test_platt_output_stays_in_the_unit_interval():
    p, y = _miscalibrated(seed=1)
    out = PlattCalibrator().fit(p, y).transform(p)
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_platt_preserves_shape():
    p, y = _miscalibrated(n=100, seed=2)
    cal = PlattCalibrator().fit(p, y)
    assert cal.transform(p.reshape(20, 5)).shape == (20, 5)


def test_platt_is_a_noop_on_a_single_class():
    """A degenerate target cannot fit a calibrator; passing through is the honest fallback."""
    p = np.full(50, 0.7)
    cal = PlattCalibrator().fit(p, np.zeros(50, dtype=int))
    assert not cal.fitted
    assert np.allclose(cal.transform(p), p)


def test_unfitted_platt_passes_probabilities_through():
    p = np.linspace(0.1, 0.9, 9)
    assert np.allclose(PlattCalibrator().transform(p), p)


def test_temperature_scaler_recovers_a_known_temperature():
    rng = np.random.default_rng(3)
    n, k = 600, 4
    logits = rng.normal(size=(n, k)) * 3.0
    probs = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    targets = np.array([rng.choice(k, p=row) for row in probs])
    scaler = TemperatureScaler().fit(logits * 3.0, targets)
    assert 1.5 < scaler.temperature < 4.0  # should shrink the inflated logits


def test_temperature_scaler_output_is_a_distribution():
    rng = np.random.default_rng(4)
    logits = rng.normal(size=(50, 5))
    targets = rng.integers(0, 5, 50)
    out = TemperatureScaler().fit(logits, targets).transform(logits)
    assert out.shape == (50, 5)
    assert np.allclose(out.sum(axis=1), 1.0)
    assert (out >= 0.0).all()


def test_temperature_of_one_is_the_identity_softmax():
    logits = np.array([[1.0, 2.0, 3.0]])
    out = TemperatureScaler(temperature=1.0).transform(logits)
    expected = np.exp(logits - logits.max())
    expected /= expected.sum()
    assert np.allclose(out, expected)
