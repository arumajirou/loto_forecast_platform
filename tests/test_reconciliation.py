"""Reconciled forecasts must be exactly coherent."""

import sys
import types

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
    assert full[0] == 37.0
    assert full[1] + full[2] == 37.0
    assert full[-1] == 1.0


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
    base[0] = 100.0
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


def test_upstream_dependency_is_optional_but_never_constructor_only():
    h = build_number_hierarchy(G)
    out = reconcile_with_hierarchicalforecast(np.ones((h.n_total, 1)), h)
    assert out["status"] in {"VERIFIED", "UNAVAILABLE"}
    if out["status"] == "VERIFIED":
        assert out["actual_execution"] is True
        assert out["coherence_error"] <= out["coherence_tolerance"]
    else:
        assert out["actual_execution"] is False
        assert "uv sync" in out["remedy"]


def _install_fake_hierarchicalforecast(
    monkeypatch: pytest.MonkeyPatch,
    *,
    classes: dict[str, type],
    strict: bool,
) -> None:
    package = types.ModuleType("hierarchicalforecast")
    package.__path__ = []
    package.__version__ = "1.5.1-test"
    methods = types.ModuleType("hierarchicalforecast.methods")
    utils = types.ModuleType("hierarchicalforecast.utils")
    for name, cls in classes.items():
        setattr(methods, name, cls)
    utils.is_strictly_hierarchical = lambda _s, _tags: strict
    package.methods = methods
    package.utils = utils
    monkeypatch.setitem(sys.modules, "hierarchicalforecast", package)
    monkeypatch.setitem(sys.modules, "hierarchicalforecast.methods", methods)
    monkeypatch.setitem(sys.modules, "hierarchicalforecast.utils", utils)


def test_upstream_delegate_executes_fit_predict_and_verifies(monkeypatch):
    class FakeMinTrace:
        is_strictly_hierarchical = False
        is_sparse_method = False
        instances = []

        def __init__(self, method):
            self.method = method
            self.insample = False
            self.called = False
            self.__class__.instances.append(self)

        def fit_predict(self, S, y_hat, y_insample=None, y_hat_insample=None, tags=None):
            self.called = True
            assert y_insample is None
            assert y_hat_insample is None
            assert "number" in tags
            return {"mean": S @ y_hat[-S.shape[1] :]}

    _install_fake_hierarchicalforecast(
        monkeypatch,
        classes={"MinTrace": FakeMinTrace},
        strict=False,
    )
    h = build_number_hierarchy(G)
    base = np.arange(h.n_total, dtype=float).reshape(-1, 1)
    out = reconcile_with_hierarchicalforecast(base, h)

    assert out["status"] == "VERIFIED"
    assert out["actual_execution"] is True
    assert out["upstream_options"] == {"method": "ols"}
    assert out["coherence_error"] <= out["coherence_tolerance"]
    assert FakeMinTrace.instances[0].called is True


def test_upstream_strict_method_rejects_grouped_number_hierarchy(monkeypatch):
    class FakeTopDown:
        is_strictly_hierarchical = True
        is_sparse_method = False

        def __init__(self, method):
            raise AssertionError("constructor must not run for an incompatible hierarchy")

    _install_fake_hierarchicalforecast(
        monkeypatch,
        classes={"TopDown": FakeTopDown},
        strict=False,
    )
    h = build_number_hierarchy(G)
    out = reconcile_with_hierarchicalforecast(
        np.ones((h.n_total, 1)),
        h,
        method="TopDown",
    )

    assert out["status"] == "UNSUPPORTED_HIERARCHY"
    assert out["actual_execution"] is False


def test_upstream_insample_method_fails_closed_without_inputs(monkeypatch):
    class FakeERM:
        is_strictly_hierarchical = False
        is_sparse_method = False

        def __init__(self, method):
            self.method = method
            self.insample = True

        def fit_predict(self, S, y_hat, y_insample, y_hat_insample):
            raise AssertionError("fit_predict must not run without in-sample arrays")

    _install_fake_hierarchicalforecast(
        monkeypatch,
        classes={"ERM": FakeERM},
        strict=False,
    )
    h = build_number_hierarchy(G)
    out = reconcile_with_hierarchicalforecast(
        np.ones((h.n_total, 1)),
        h,
        method="ERM",
    )

    assert out["status"] == "REQUIRES_INSAMPLE"
    assert out["actual_execution"] is False


def test_upstream_incoherent_output_is_not_certified(monkeypatch):
    class FakeMinTrace:
        is_strictly_hierarchical = False
        is_sparse_method = False

        def __init__(self, method):
            self.method = method
            self.insample = False

        def fit_predict(self, S, y_hat):
            return {"mean": y_hat.copy()}

    _install_fake_hierarchicalforecast(
        monkeypatch,
        classes={"MinTrace": FakeMinTrace},
        strict=False,
    )
    h = build_number_hierarchy(G)
    base = np.zeros((h.n_total, 1))
    base[0] = 100.0
    out = reconcile_with_hierarchicalforecast(base, h)

    assert out["status"] == "VALIDATION_FAILED"
    assert out["actual_execution"] is True
    assert out["coherence_error"] > out["coherence_tolerance"]
