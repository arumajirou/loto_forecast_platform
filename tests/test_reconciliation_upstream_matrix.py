"""Coverage matrix for every registered HierarchicalForecast reconciler."""

from __future__ import annotations

import sys
import types
from collections.abc import Mapping

import numpy as np
import pytest

from loto.game.geometry import geometry_for
from loto.reconciliation.hierarchy import (
    UPSTREAM_METHODS,
    build_number_hierarchy,
    reconcile_with_hierarchicalforecast,
)

G = geometry_for("loto7")

EXECUTABLE_METHODS: Mapping[str, dict[str, object]] = {
    "BottomUp": {},
    "BottomUpSparse": {},
    "MinTrace": {"method": "ols"},
    "MinTraceSparse": {"method": "ols"},
    "OptimalCombination": {"method": "ols"},
}
STRICT_ONLY_METHODS = {
    "TopDown",
    "TopDownSparse",
    "MiddleOut",
    "MiddleOutSparse",
}


def _install_fake_hierarchicalforecast(
    monkeypatch: pytest.MonkeyPatch,
    *,
    classes: dict[str, type],
    strict: bool,
) -> None:
    package = types.ModuleType("hierarchicalforecast")
    package.__path__ = []
    package.__version__ = "1.5.1-matrix-test"
    methods = types.ModuleType("hierarchicalforecast.methods")
    utils = types.ModuleType("hierarchicalforecast.utils")
    for name, cls in classes.items():
        setattr(methods, name, cls)

    def fake_is_strictly_hierarchical(_s, _tags):
        return strict

    utils.is_strictly_hierarchical = fake_is_strictly_hierarchical
    package.methods = methods
    package.utils = utils
    monkeypatch.setitem(sys.modules, "hierarchicalforecast", package)
    monkeypatch.setitem(sys.modules, "hierarchicalforecast.methods", methods)
    monkeypatch.setitem(sys.modules, "hierarchicalforecast.utils", utils)


def _dense_summing_matrix(summing_matrix):
    if hasattr(summing_matrix, "toarray"):
        return np.asarray(summing_matrix.toarray(), dtype=float)
    return np.asarray(summing_matrix, dtype=float)


def _make_executable_reconciler(*, sparse: bool, insample: bool = False):
    class FakeReconciler:
        is_strictly_hierarchical = False
        is_sparse_method = sparse
        instances: list[FakeReconciler] = []

        def __init__(self, **options):
            self.options = options
            self.insample = insample
            self.received_sparse = False
            self.received_actuals = None
            self.received_fitted = None
            self.__class__.instances.append(self)

        def fit_predict(
            self,
            S,
            y_hat,
            y_insample=None,
            y_hat_insample=None,
            tags=None,
        ):
            self.received_sparse = hasattr(S, "toarray")
            self.received_actuals = y_insample
            self.received_fitted = y_hat_insample
            assert tags is not None
            dense_s = _dense_summing_matrix(S)
            return {"mean": dense_s @ y_hat[-dense_s.shape[1] :]}

    return FakeReconciler


def test_registered_upstream_method_partition_is_complete() -> None:
    covered = set(EXECUTABLE_METHODS) | STRICT_ONLY_METHODS | {"ERM"}
    assert covered == set(UPSTREAM_METHODS)
    assert len(UPSTREAM_METHODS) == len(set(UPSTREAM_METHODS)) == 10


@pytest.mark.parametrize(
    ("method", "expected_options"),
    EXECUTABLE_METHODS.items(),
)
def test_every_grouped_compatible_method_executes_and_verifies(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    expected_options: dict[str, object],
) -> None:
    fake_class = _make_executable_reconciler(sparse=method.endswith("Sparse"))
    _install_fake_hierarchicalforecast(
        monkeypatch,
        classes={method: fake_class},
        strict=False,
    )
    hierarchy = build_number_hierarchy(G)
    base = np.arange(hierarchy.n_total, dtype=float).reshape(-1, 1)

    result = reconcile_with_hierarchicalforecast(base, hierarchy, method=method)

    assert result["status"] == "VERIFIED"
    assert result["actual_execution"] is True
    assert result["upstream_options"] == expected_options
    assert result["finite"] is True
    assert result["coherence_error"] <= result["coherence_tolerance"]
    instance = fake_class.instances[0]
    assert instance.options == expected_options
    assert instance.received_sparse is method.endswith("Sparse")


@pytest.mark.parametrize("method", sorted(STRICT_ONLY_METHODS))
def test_every_strict_only_method_rejects_grouped_number_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    class StrictOnlyReconciler:
        is_strictly_hierarchical = True
        is_sparse_method = method.endswith("Sparse")

        def __init__(self, **_options):
            raise AssertionError("constructor must not run for grouped hierarchies")

    _install_fake_hierarchicalforecast(
        monkeypatch,
        classes={method: StrictOnlyReconciler},
        strict=False,
    )
    hierarchy = build_number_hierarchy(G)

    result = reconcile_with_hierarchicalforecast(
        np.ones((hierarchy.n_total, 1)),
        hierarchy,
        method=method,
    )

    assert result["status"] == "UNSUPPORTED_HIERARCHY"
    assert result["actual_execution"] is False
    assert result["hierarchy_is_strict"] is False


def test_erm_requires_and_accepts_paired_insample_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_class = _make_executable_reconciler(sparse=False, insample=True)
    _install_fake_hierarchicalforecast(
        monkeypatch,
        classes={"ERM": fake_class},
        strict=False,
    )
    hierarchy = build_number_hierarchy(G)
    base = np.arange(hierarchy.n_total, dtype=float).reshape(-1, 1)

    missing = reconcile_with_hierarchicalforecast(base, hierarchy, method="ERM")
    assert missing["status"] == "REQUIRES_INSAMPLE"
    assert missing["actual_execution"] is False

    actuals = np.ones((hierarchy.n_total, 8), dtype=float)
    fitted = np.full((hierarchy.n_total, 8), 0.5, dtype=float)
    verified = reconcile_with_hierarchicalforecast(
        base,
        hierarchy,
        method="ERM",
        insample_actuals=actuals,
        insample_forecasts=fitted,
    )

    assert verified["status"] == "VERIFIED"
    assert verified["upstream_options"] == {"method": "closed"}
    instance = fake_class.instances[-1]
    assert instance.received_actuals is actuals
    assert instance.received_fitted is fitted


def test_method_options_override_is_forwarded_without_silent_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_class = _make_executable_reconciler(sparse=False)
    _install_fake_hierarchicalforecast(
        monkeypatch,
        classes={"MinTrace": fake_class},
        strict=False,
    )
    hierarchy = build_number_hierarchy(G)
    options = {"method": "wls_struct", "nonnegative": False, "num_threads": 1}

    result = reconcile_with_hierarchicalforecast(
        np.ones((hierarchy.n_total, 1)),
        hierarchy,
        method="MinTrace",
        method_options=options,
    )

    assert result["status"] == "VERIFIED"
    assert result["upstream_options"] == options
    assert fake_class.instances[0].options == options
