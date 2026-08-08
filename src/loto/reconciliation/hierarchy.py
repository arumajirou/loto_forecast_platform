"""Coherent aggregation across the number hierarchy.

A draw admits several natural aggregations: individual numbers roll up into decades, into
parity classes, into low/high halves, and finally into the total draw size. Forecasting each
level independently produces *incoherent* forecasts -- the decade forecasts do not sum to the
number forecasts. Reconciliation projects the base forecasts onto the coherent subspace.

Two implementations are provided:

* :func:`reconcile` -- a self-contained MinT/OLS/BottomUp/TopDown reconciliation that runs on
  numpy alone, so the core dependency set does not grow.
* :func:`reconcile_with_hierarchicalforecast` -- executes Nixtla's
  ``hierarchicalforecast`` when installed and verifies the returned forecast.

Both implementations verify ``S @ bottom == full`` rather than assuming coherence.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

import numpy as np

from loto.game.geometry import GameGeometry

__all__ = [
    "Hierarchy",
    "build_number_hierarchy",
    "reconcile",
    "coherence_error",
    "reconcile_with_hierarchicalforecast",
    "AVAILABLE_METHODS",
    "UPSTREAM_METHODS",
]

AVAILABLE_METHODS: tuple[str, ...] = (
    "bottom_up",
    "top_down",
    "ols",
    "wls_struct",
    "mint_shrink",
)
UPSTREAM_METHODS: tuple[str, ...] = (
    "BottomUp",
    "BottomUpSparse",
    "TopDown",
    "TopDownSparse",
    "MiddleOut",
    "MiddleOutSparse",
    "MinTrace",
    "MinTraceSparse",
    "OptimalCombination",
    "ERM",
)

_UPSTREAM_DEFAULT_OPTIONS: dict[str, dict[str, object]] = {
    "BottomUp": {},
    "BottomUpSparse": {},
    "TopDown": {"method": "forecast_proportions"},
    "TopDownSparse": {"method": "forecast_proportions"},
    "MiddleOut": {"top_down_method": "forecast_proportions"},
    "MiddleOutSparse": {"top_down_method": "forecast_proportions"},
    "MinTrace": {"method": "ols"},
    "MinTraceSparse": {"method": "ols"},
    "OptimalCombination": {"method": "ols"},
    "ERM": {"method": "closed"},
}


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
        lam = float(
            np.clip(
                1.0 - denom / (denom + float(np.sum(diag**2)) + 1e-12),
                0.0,
                1.0,
            )
        )
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


def _as_forecast_matrix(values: np.ndarray, hierarchy: Hierarchy, *, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    if matrix.ndim != 2:
        raise ValueError(f"{name} must be one- or two-dimensional")
    if matrix.shape[0] != hierarchy.n_total:
        raise ValueError(
            f"{name} expected {hierarchy.n_total} series, got {matrix.shape[0]}"
        )
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} contains NaN or Inf")
    return matrix


def _hierarchy_tags(hierarchy: Hierarchy) -> dict[str, np.ndarray]:
    tags: dict[str, list[int]] = {}
    for index, label in enumerate(hierarchy.labels):
        level = label if label == "total" else label.split("/", maxsplit=1)[0]
        tags.setdefault(level, []).append(index)
    return {name: np.asarray(indices, dtype=int) for name, indices in tags.items()}


def _filtered_call_kwargs(callable_object: Any, values: dict[str, object]) -> dict[str, object]:
    parameters = inspect.signature(callable_object).parameters
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return values
    return {key: value for key, value in values.items() if key in parameters}


def reconcile_with_hierarchicalforecast(
    base_forecasts: np.ndarray,
    hierarchy: Hierarchy,
    *,
    method: str = "MinTrace",
    method_options: dict[str, object] | None = None,
    insample_actuals: np.ndarray | None = None,
    insample_forecasts: np.ndarray | None = None,
    coherence_tolerance: float = 1e-8,
) -> dict[str, object]:
    """Execute and verify Nixtla ``hierarchicalforecast`` reconciliation.

    The optional dependency is fail-closed: unavailable packages, incompatible grouped
    hierarchies, missing in-sample arrays, constructor errors, execution errors, non-finite
    results, shape mismatches, and incoherent outputs receive distinct statuses.
    """
    base = _as_forecast_matrix(base_forecasts, hierarchy, name="base_forecasts")
    if coherence_tolerance < 0:
        raise ValueError("coherence_tolerance must be non-negative")
    if (insample_actuals is None) != (insample_forecasts is None):
        raise ValueError(
            "insample_actuals and insample_forecasts must be supplied together"
        )

    actuals: np.ndarray | None = None
    fitted: np.ndarray | None = None
    if insample_actuals is not None and insample_forecasts is not None:
        actuals = _as_forecast_matrix(
            insample_actuals,
            hierarchy,
            name="insample_actuals",
        )
        fitted = _as_forecast_matrix(
            insample_forecasts,
            hierarchy,
            name="insample_forecasts",
        )
        if actuals.shape != fitted.shape:
            raise ValueError("in-sample actual and forecast shapes must match")

    if method not in UPSTREAM_METHODS:
        raise ValueError(
            f"hierarchicalforecast has no supported method {method!r}; "
            f"available={list(UPSTREAM_METHODS)}"
        )

    try:
        import hierarchicalforecast
        import hierarchicalforecast.methods as hfm
        from hierarchicalforecast.utils import is_strictly_hierarchical
    except ImportError as exc:
        return {
            "status": "UNAVAILABLE",
            "method": method,
            "actual_execution": False,
            "error": f"{type(exc).__name__}: {exc}",
            "remedy": "uv sync --extra full",
        }

    if not hasattr(hfm, method):
        raise ValueError(f"installed hierarchicalforecast has no method {method!r}")

    tags = _hierarchy_tags(hierarchy)
    s_dense = np.asarray(hierarchy.summing_matrix, dtype=float)
    try:
        hierarchy_is_strict = bool(is_strictly_hierarchical(s_dense, tags))
    except Exception as exc:
        return {
            "status": "VALIDATION_FAILED",
            "method": method,
            "actual_execution": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    reconciler_class = getattr(hfm, method)
    strict_only = bool(
        getattr(reconciler_class, "is_strictly_hierarchical", False)
    )
    if strict_only and not hierarchy_is_strict:
        return {
            "status": "UNSUPPORTED_HIERARCHY",
            "method": method,
            "actual_execution": False,
            "hierarchy_is_strict": False,
            "error": (
                f"{method} requires a strictly hierarchical tree, but the number hierarchy "
                "contains grouped parity and decade aggregations"
            ),
        }

    options = dict(_UPSTREAM_DEFAULT_OPTIONS[method])
    options.update(method_options or {})
    if method in {"MiddleOut", "MiddleOutSparse"} and "middle_level" not in options:
        return {
            "status": "CONFIGURATION_REQUIRED",
            "method": method,
            "actual_execution": False,
            "hierarchy_is_strict": hierarchy_is_strict,
            "error": "middle_level is required for MiddleOut reconciliation",
        }

    try:
        reconciler = reconciler_class(**options)
    except (TypeError, ValueError) as exc:
        return {
            "status": "CONFIGURATION_ERROR",
            "method": method,
            "actual_execution": False,
            "hierarchy_is_strict": hierarchy_is_strict,
            "upstream_options": options,
            "error": f"{type(exc).__name__}: {exc}",
        }

    requires_insample = bool(getattr(reconciler, "insample", False))
    if requires_insample and (actuals is None or fitted is None):
        return {
            "status": "REQUIRES_INSAMPLE",
            "method": method,
            "actual_execution": False,
            "hierarchy_is_strict": hierarchy_is_strict,
            "requires_insample": True,
            "upstream_options": options,
            "error": "selected reconciliation method requires in-sample actuals and forecasts",
        }

    upstream_s: object = s_dense
    if bool(getattr(reconciler, "is_sparse_method", False)):
        try:
            from scipy import sparse
        except ImportError as exc:
            return {
                "status": "UNAVAILABLE",
                "method": method,
                "actual_execution": False,
                "error": f"{type(exc).__name__}: {exc}",
                "remedy": "uv sync --extra full",
            }
        upstream_s = sparse.csr_matrix(s_dense)

    call_values: dict[str, object] = {
        "S": upstream_s,
        "y_hat": base,
        "y_insample": actuals,
        "y_hat_insample": fitted,
        "tags": tags,
    }
    try:
        raw_result = reconciler.fit_predict(
            **_filtered_call_kwargs(reconciler.fit_predict, call_values)
        )
    except Exception as exc:  # upstream methods raise several library-specific exception types
        return {
            "status": "EXECUTION_FAILED",
            "method": method,
            "actual_execution": True,
            "hierarchy_is_strict": hierarchy_is_strict,
            "requires_insample": requires_insample,
            "upstream_options": options,
            "error": f"{type(exc).__name__}: {exc}",
        }

    reconciled_value = raw_result.get("mean") if isinstance(raw_result, dict) else raw_result
    try:
        reconciled = _as_forecast_matrix(
            np.asarray(reconciled_value),
            hierarchy,
            name="reconciled_forecasts",
        )
    except (TypeError, ValueError) as exc:
        return {
            "status": "VALIDATION_FAILED",
            "method": method,
            "actual_execution": True,
            "hierarchy_is_strict": hierarchy_is_strict,
            "requires_insample": requires_insample,
            "upstream_options": options,
            "error": f"{type(exc).__name__}: {exc}",
        }

    bottom = reconciled[-hierarchy.n_bottom :]
    error = coherence_error(reconciled, bottom, hierarchy)
    status = "VERIFIED" if error <= coherence_tolerance else "VALIDATION_FAILED"
    return {
        "status": status,
        "method": method,
        "actual_execution": True,
        "upstream_version": getattr(hierarchicalforecast, "__version__", "UNKNOWN"),
        "hierarchy_is_strict": hierarchy_is_strict,
        "requires_insample": requires_insample,
        "upstream_options": options,
        "reconciler": repr(reconciler),
        "bottom": bottom,
        "reconciled": reconciled,
        "finite": bool(np.isfinite(reconciled).all()),
        "shape": list(reconciled.shape),
        "coherence_error": error,
        "coherence_tolerance": coherence_tolerance,
        "base_incoherence": coherence_error(
            base,
            base[-hierarchy.n_bottom :],
            hierarchy,
        ),
    }
