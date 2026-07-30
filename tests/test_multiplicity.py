"""Multiple-comparison control. Without it, a model sweep always finds a winner."""
import numpy as np
import pytest

from loto.evaluation.multiplicity import (
    benjamini_hochberg,
    correct,
    family_wise_false_positive_probability,
    holm,
    paired_bootstrap_p,
    romano_wolf,
)


def test_naive_sweep_false_positive_rate_is_catastrophic():
    assert family_wise_false_positive_probability(100, 0.05) > 0.99
    assert family_wise_false_positive_probability(1, 0.05) == pytest.approx(0.05)
    assert family_wise_false_positive_probability(0, 0.05) == 0.0


def test_holm_is_monotone_and_conservative():
    p = [0.001, 0.01, 0.04, 0.5]
    c = holm(p)
    adj = list(c.adjusted_p)
    assert adj == sorted(adj)
    assert all(a >= b for a, b in zip(adj, p))


def test_holm_rejects_nothing_when_all_p_are_marginal():
    """20 models each at raw p=0.04 must yield zero discoveries."""
    c = holm([0.04] * 20)
    assert c.n_rejected == 0


def test_bh_is_more_powerful_than_holm():
    p = [0.001, 0.002, 0.004, 0.008, 0.2, 0.4]
    assert benjamini_hochberg(p).n_rejected >= holm(p).n_rejected


def test_bh_adjusted_p_is_monotone():
    adj = list(benjamini_hochberg([0.5, 0.01, 0.3, 0.001]).adjusted_p)
    order = np.argsort([0.5, 0.01, 0.3, 0.001])
    assert list(np.asarray(adj)[order]) == sorted(np.asarray(adj)[order])


def test_correction_rejects_invalid_input():
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        holm([-0.1])
    with pytest.raises(ValueError, match="alpha"):
        holm([0.1], alpha=0.0)
    with pytest.raises(ValueError, match="unknown method"):
        correct([0.1], method="bogus")


def test_empty_input_is_handled():
    assert holm([]).n_hypotheses == 0
    assert benjamini_hochberg([]).n_rejected == 0


def test_romano_wolf_finds_nothing_on_pure_noise():
    """40 candidates identical in distribution to the baseline -> zero discoveries."""
    rng = np.random.default_rng(0)
    base = rng.normal(size=120)
    cand = rng.normal(size=(40, 120))
    c = romano_wolf(cand, base, alpha=0.05, n_boot=400, seed=1)
    assert c.n_rejected == 0


def test_romano_wolf_detects_a_genuinely_better_model():
    rng = np.random.default_rng(3)
    base = rng.normal(loc=1.0, scale=0.5, size=200)
    cand = np.vstack([rng.normal(loc=0.2, scale=0.5, size=200),
                      rng.normal(loc=1.0, scale=0.5, size=200)])
    c = romano_wolf(cand, base, alpha=0.05, n_boot=600, seed=2)
    assert c.rejected[0] and not c.rejected[1]


def test_romano_wolf_rejects_misaligned_shapes():
    with pytest.raises(ValueError, match="shape"):
        romano_wolf(np.zeros((3, 10)), np.zeros(9))


def test_paired_bootstrap_reports_interval_and_n():
    rng = np.random.default_rng(11)
    a = rng.normal(0.0, 1.0, 80)
    b = rng.normal(0.5, 1.0, 80)
    out = paired_bootstrap_p(a, b, n_boot=500, seed=5)
    assert out["delta"] < 0
    assert out["ci_low"] < out["delta"] < out["ci_high"]
    assert out["n"] == 80


def test_paired_bootstrap_on_a_constant_difference_collapses_the_interval():
    """A deterministic offset has zero bootstrap variance; the interval must be a point."""
    a = np.arange(50, dtype=float)
    out = paired_bootstrap_p(a, a + 0.5, n_boot=200, seed=1)
    assert out["ci_low"] == pytest.approx(out["ci_high"])
    assert out["delta"] == pytest.approx(-0.5)


def test_paired_bootstrap_requires_alignment():
    with pytest.raises(ValueError, match="align"):
        paired_bootstrap_p([1, 2, 3], [1, 2])
