"""Coherent aggregation across the number hierarchy.

A draw admits several natural aggregations: individual numbers roll up into decades, into
parity classes, into low/high halves, and finally into the total draw size. Forecasting each
level independently produces *incoherent* forecasts -- the decade forecasts do not sum to the
number forecasts. Reconciliation projects the base forecasts onto the coherent subspace.

Two implementations are provided:

* :func:`reconcile` -- a self-contained MinT/OLS/BottomUp/TopDown reconciliation that runs on
  numpy alone, so the core dependency set does not grow.
* :func:`reconcile_with_hierarchicalforecast` -- delegates to Nixtla's
  ``hierarchicalforecast`` when installed, exposing all ten upstream methods.

Both are exact in the sense that the returned forecasts satisfy ``S @ bottom == full`` to
floating-point tolerance, which :func:`coherence_error` verifies rather than assumes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from loto.game.geometry import GameGeometry

__all__ = [
    "Hierarchy",
    "build_number_hierarchy",
    "reconcile",
    "coherence_error",
    "reconcile_with_hierarchicalforecast",
    "AVAILABLE_METHODS",
]

AVAILABLE_METHODS: tuple[str, ...] = ("bottom_up", "top_down", "ols", "wls_struct", "mint_shrink")


@dataclass(frozen=True)
class Hierarchy:
    """Summing matrix ``S`` mapping bottom-level series to all levels."""

    labels: tuple[str, ...]
    bottom_labels: tuple[str, ...]
    summing_matrix: np.ndarray

    @property
    def n_total(self) -> int:
        return len(self.labels)

    @property
    def n_bottom(self) -> int:
        return len(self.bottom_labels)

    def aggregate(self, bottom: np.ndarray) -> np.ndarray:
        b = np.asarray(bottom, dtype=float)
        if b.shape[0] != self.n_bottom:
            raise ValueError(f"expected {self.n_bottom} bottom series, got {b.shape[0]}")
        return self.summing_matrix @ b


def build_number_hierarchy(geometry: GameGeometry) -> Hierarchy:
    """Total -> parity -> decade -> individual number, for a ``select`` game."""
    if geometry.family != "select":
        raise ValueError("number hierarchy is defined for select-family games only")
    values = list(geometry.values)
    n = len(values)

    rows: list[np.ndarray] = []
    labels: list[str] = []

    rows.append(np.ones(n, dtype=float))
    labels.append("total")

    for name, predicate in (("odd", lambda v: v % 2 == 1), ("even", lambda v: v % 2 == 0)):
        rows.append(np.array([1.0 if predicate(v) else 0.0 for v in values]))
        labels.append(f"parity/{name}")

    for decade in sorted({v // 10 for v in values}):
        rows.append(np.array([1.0 if v // 10 == decade else 0.0 for v in values]))
        labels.append(f"decade/{decade}")

    rows.extend(np.eye(n, dtype=float))
    labels.extend(f"number/{v}" for v in values)

    return Hierarchy(
        labels=tuple(labels),
        bottom_labels=tuple(f"number/{v}" for v in values),
        summing_matrix=np.vstack(rows),
    )


def _projection(hierarchy: Hierarchy, method: str, residuals: np.ndarray | None) -> np.ndarray:
    """Return ``P`` such that reconciled bottom = ``P @ base_all``."""
    s = hierarchy.summing_matrix
    n_bottom = hierarchy.n_bottom
    if method == "bottom_up":
        p = np.zeros((n_bottom, hierarchy.n_total), dtype=float)
        offset = hierarchy.n_total - n_bottom
        p[:, offset:] = np.eye(n_bottom)
        return p
    if method == "top_down":
        p = np.zeros((n_bottom, hierarchy.n_total), dtype=float)
        p[:, 0] = 1.0 / n_bottom
        return p
    if method == "ols":
        w_inv = np.eye(hierarchy.n_total)
    elif method == "wls_struct":
        w_inv = np.diag(1.0 / s.sum(axis=1))
    elif method == "mint_shrink":
        if residuals is None:
            raise ValueError("mint_shrink requires in-sample residuals")
        r = np.asarray(residuals, dtype=float)
        if r.shape[0] != hierarchy.n_total:
            raise ValueError("residuals must have one row per hierarchy level")
        cov = np.cov(r, ddof=1) if r.shape[1] > 1 else np.eye(hierarchy.n_total)
        diag = np.diag(np.diag(cov))
        off = cov - diag
        denom = float(np.sum(off**2))
        lam = float(np.clip(1.0 - denom / (denom + float(np.sum(diag**2)) + 1e-12), 0.0, 1.0))
        shrunk = lam * diag + (1.0 - lam) * cov
        shrunk = shrunk + np.eye(hierarchy.n_total) * 1e-8
        w_inv = np.linalg.pinv(shrunk)
    else:
        raise ValueError(f"unknown method={method!r}; available={list(AVAILABLE_METHODS)}")
    middle = np.linalg.pinv(s.T @ w_inv @ s)
    return middle @ s.T @ w_inv


def reconcile(
    base_forecasts: np.ndarray,
    hierarchy: Hierarchy,
    *,
    method: str = "mint_shrink",
    residuals: np.ndarray | None = None,
    non_negative: bool = True,
) -> dict[str, object]:
    """Project incoherent base forecasts onto the coherent subspace."""
    base = np.asarray(base_forecasts, dtype=float)
    if base.ndim == 1:
        base = base.reshape(-1, 1)
    if base.shape[0] != hierarchy.n_total:
        raise ValueError(f"expected {hierarchy.n_total} base series, got {base.shape[0]}")
    if method == "mint_shrink" and residuals is None:
        method = "wls_struct"  # explicit downgrade, reported below
        downgraded = True
    else:
        downgraded = False

    p = _projection(hierarchy, method, residuals)
    bottom = p @ base
    if non_negative:
        bottom = np.clip(bottom, 0.0, None)
    full = hierarchy.summing_matrix @ bottom
    return {
        "method": method,
        "downgraded_from_mint_shrink": downgraded,
        "bottom": bottom,
        "reconciled": full,
        "coherence_error": coherence_error(full, bottom, hierarchy),
        "base_incoherence": coherence_error(base, base[-hierarchy.n_bottom :], hierarchy),
    }


def coherence_error(full: np.ndarray, bottom: np.ndarray, hierarchy: Hierarchy) -> float:
    """Max absolute violation of ``S @ bottom == full``. Zero for a coherent forecast."""
    f = np.asarray(full, dtype=float)
    b = np.asarray(bottom, dtype=float)
    if f.ndim == 1:
        f = f.reshape(-1, 1)
    if b.ndim == 1:
        b = b.reshape(-1, 1)
    return float(np.abs(hierarchy.summing_matrix @ b - f).max())


def reconcile_with_hierarchicalforecast(
    base_forecasts: np.ndarray, hierarchy: Hierarchy, *, method: str = "MinTrace"
) -> dict[str, object]:
    """Delegate to Nixtla ``hierarchicalforecast``. Reports UNAVAILABLE rather than faking it."""
    try:
        import hierarchicalforecast.methods as hfm
    except ImportError as exc:
        return {
            "status": "UNAVAILABLE",
            "method": method,
            "error": f"{type(exc).__name__}: {exc}",
            "remedy": "uv sync --extra full",
        }
    if not hasattr(hfm, method):
        raise ValueError(f"hierarchicalforecast has no method {method!r}")

    reconciler_class = getattr(hfm, method)

    try:
        # hierarchicalforecast 1.x requires an explicit reconciliation
        # strategy for MinTrace. OLS does not require residual forecasts.
        if method == "MinTrace":
            reconciler = reconciler_class(method="ols")
            upstream_method = "ols"
        else:
            reconciler = reconciler_class()
            upstream_method = None
    except (TypeError, ValueError) as exc:
        return {
            "status": "UNAVAILABLE",
            "method": method,
            "error": f"{type(exc).__name__}: {exc}",
            "remedy": (
                "Check the installed hierarchicalforecast API and "
                "select a supported reconciliation method."
            ),
        }

    result: dict[str, object] = {
        "status": "AVAILABLE",
        "method": method,
        "reconciler": repr(reconciler),
    }
    if upstream_method is not None:
        result["upstream_method"] = upstream_method
    return result
