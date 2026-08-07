"""Reconciled forecasts must be exactly coherent."""

import numpy as np
import pytest

from loto.game.geometry import geometry_for
from loto.reconciliation.hierarchy import (
    AVAILABLE_METHODS,
    build_number_hierarchy,
    coherence_error,
    reconcile,
    reconcile_with_hierarchicalforecast,
)

G = geometry_for("loto7")


def test_hierarchy_shape():
    h = build_number_hierarchy(G)
    assert h.n_bottom == 37
    assert h.labels[0] == "total"
    assert h.summing_matrix.shape == (h.n_total, 37)


def test_summing_matrix_aggregates_correctly():
    h = build_number_hierarchy(G)
    bottom = np.ones(37)
    full = h.aggregate(bottom)
    assert full[0] == 37.0  # total
    assert full[1] + full[2] == 37.0  # odd + even
    assert full[-1] == 1.0  # individual number


@pytest.mark.parametrize("method", AVAILABLE_METHODS)
def test_every_method_returns_a_coherent_forecast(method):
    h = build_number_hierarchy(G)
    rng = np.random.default_rng(0)
    base = rng.uniform(0.0, 1.0, size=(h.n_total, 1))
    residuals = rng.normal(size=(h.n_total, 30)) if method == "mint_shrink" else None
    out = reconcile(base, h, method=method, residuals=residuals)
    assert out["coherence_error"] < 1e-8


def test_incoherent_base_is_detected_before_reconciliation():
    h = build_number_hierarchy(G)
    base = np.zeros((h.n_total, 1))
    base[0] = 100.0  # total says 100, bottom says 0
    out = reconcile(base, h, method="ols")
    assert out["base_incoherence"] > 1.0
    assert out["coherence_error"] < 1e-8


def test_mint_shrink_downgrades_explicitly_without_residuals():
    h = build_number_hierarchy(G)
    out = reconcile(np.ones((h.n_total, 1)), h, method="mint_shrink", residuals=None)
    assert out["downgraded_from_mint_shrink"] is True
    assert out["method"] == "wls_struct"


def test_non_negativity_is_enforced():
    h = build_number_hierarchy(G)
    rng = np.random.default_rng(1)
    base = rng.normal(-5.0, 1.0, size=(h.n_total, 1))
    out = reconcile(base, h, method="ols", non_negative=True)
    assert (out["bottom"] >= 0.0).all()


def test_unknown_method_is_rejected():
    h = build_number_hierarchy(G)
    with pytest.raises(ValueError, match="unknown method"):
        reconcile(np.ones((h.n_total, 1)), h, method="magic")


def test_wrong_base_length_is_rejected():
    h = build_number_hierarchy(G)
    with pytest.raises(ValueError, match="expected"):
        reconcile(np.ones((5, 1)), h)


def test_digit_games_have_no_number_hierarchy():
    with pytest.raises(ValueError, match="select-family"):
        build_number_hierarchy(geometry_for("numbers3"))


def test_coherence_error_of_a_coherent_pair_is_zero():
    h = build_number_hierarchy(G)
    bottom = np.ones((37, 1))
    assert coherence_error(h.aggregate(bottom), bottom, h) == pytest.approx(0.0)


def test_upstream_delegation_reports_unavailable_rather_than_faking():
    h = build_number_hierarchy(G)
    out = reconcile_with_hierarchicalforecast(np.ones((h.n_total, 1)), h)
    assert out["status"] in ("AVAILABLE", "UNAVAILABLE")
    if out["status"] == "UNAVAILABLE":
        assert "uv sync" in out["remedy"]
