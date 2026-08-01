"""Optional solver contract tests for KPI Lab.

These tests prove that CP-SAT never silently falls back to greedy when OR-Tools is
unavailable.  The installed-backend test runs only when OR-Tools is present; the
unavailable-backend test is hermetic and runs in every environment.
"""

from __future__ import annotations

import builtins
import importlib.util

import numpy as np
import pytest

from loto.combinatorics.set_cover import SolverUnavailable, exact_min_cover_cpsat


def _fixture() -> tuple[np.ndarray, list[tuple[int, int]]]:
    targets = np.asarray([[1, 2], [1, 3], [2, 3]], dtype=np.int64)
    pool = [(1, 2), (1, 3), (2, 3)]
    return targets, pool


def test_cpsat_missing_backend_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing OR-Tools must raise a typed error, never return a greedy result."""
    targets, pool = _fixture()
    original_targets = targets.copy()
    original_pool = list(pool)
    real_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "ortools" or name.startswith("ortools."):
            raise ImportError("simulated missing OR-Tools for contract test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(SolverUnavailable) as caught:
        exact_min_cover_cpsat(
            targets,
            pool,
            target_coverage=2 / 3,
            tolerance=0,
            time_limit_seconds=1,
            workers=1,
        )

    assert caught.value.backend == "ortools.cp_sat"
    assert "simulated missing OR-Tools" in caught.value.detail
    assert "greedy" not in str(caught.value).lower()
    np.testing.assert_array_equal(targets, original_targets)
    assert pool == original_pool


@pytest.mark.skipif(
    importlib.util.find_spec("ortools") is None,
    reason="OR-Tools is optional; install the solver extra to run this branch",
)
def test_cpsat_installed_backend_returns_cpsat_result() -> None:
    """When installed, the result must identify CP-SAT rather than another algorithm."""
    targets, pool = _fixture()
    result = exact_min_cover_cpsat(
        targets,
        pool,
        target_coverage=2 / 3,
        tolerance=0,
        time_limit_seconds=5,
        workers=1,
    )
    assert result.method.startswith("cpsat:")
    assert result.n_tickets >= 1
    assert result.coverage >= 2 / 3
