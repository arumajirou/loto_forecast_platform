"""Coverage estimation that cannot be overfitted.

Under the uniform i.i.d. draw model the coverage of a pool is a fixed property of the
pool's geometry, not of any dataset. It can therefore be estimated to arbitrary precision
by sampling the outcome space directly -- no historical draws needed, and no possibility
of fitting to them.

This gives the KPI Lab a second, independent measurement axis:

* ``monte_carlo_coverage``  -- coverage under the uniform null. Overfitting-proof.
* empirical coverage on draws -- coverage on the observed record.

If those two disagree beyond sampling error, the pool is exploiting structure in the
observed draws. That is either a real departure from uniformity or a leak, and
:mod:`loto.kpi_lab.negative_controls` is what distinguishes the two.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from loto.game.geometry import geometry_for

__all__ = [
    "CoverageEstimate",
    "uniform_outcomes",
    "monte_carlo_coverage",
    "empirical_coverage",
    "wilson_interval",
]


@dataclass(frozen=True)
class CoverageEstimate:
    """A coverage figure with its uncertainty and its provenance."""

    coverage: float
    n_samples: int
    n_tickets: int
    tolerance: int
    ci_low: float
    ci_high: float
    source: str
    seed: int | None = None

    @property
    def standard_error(self) -> float:
        if self.n_samples <= 0:
            return float("nan")
        p = self.coverage
        return math.sqrt(max(p * (1.0 - p), 0.0) / self.n_samples)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["standard_error"] = self.standard_error
        return payload


def wilson_interval(successes: int, n: int, *, z: float = 1.959963985) -> tuple[float, float]:
    """Wilson score interval. Well behaved near 0 and 1, unlike the normal approximation."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def uniform_outcomes(game: str, *, n_samples: int, seed: int = 42) -> np.ndarray:
    """``(n_samples, positions)`` array of i.i.d. uniform legal outcomes."""
    geometry = geometry_for(game)
    rng = np.random.default_rng(seed)
    if geometry.family == "select":
        values = np.arange(geometry.value_min, geometry.value_max + 1)
        out = np.empty((n_samples, geometry.positions), dtype=np.int64)
        for i in range(n_samples):
            out[i] = np.sort(rng.choice(values, size=geometry.positions, replace=False))
        return out
    return rng.integers(
        geometry.value_min,
        geometry.value_max + 1,
        size=(n_samples, geometry.positions),
        dtype=np.int64,
    )


def _covered_count(
    targets: np.ndarray, pool: np.ndarray, tolerance: int, *, chunk: int = 4096
) -> int:
    """Number of target rows covered by at least one ticket, chunked to bound memory."""
    if pool.size == 0 or targets.size == 0:
        return 0
    covered = np.zeros(targets.shape[0], dtype=bool)
    for start in range(0, pool.shape[0], chunk):
        block = pool[start : start + chunk]
        # (block, targets, positions) -> reduce over positions then over block
        diff = np.abs(targets[None, :, :] - block[:, None, :])
        hit = (diff.max(axis=2) <= tolerance).any(axis=0)
        covered |= hit
        if covered.all():
            break
    return int(covered.sum())


def monte_carlo_coverage(
    game: str,
    pool: np.ndarray | list[tuple[int, ...]],
    *,
    tolerance: int = 1,
    n_samples: int = 20000,
    seed: int = 42,
    chunk: int = 512,
) -> CoverageEstimate:
    """Coverage of ``pool`` under the uniform law, by Monte Carlo.

    This is the honest headline number for a lottery pool: it depends only on the pool's
    geometry, so it cannot be inflated by fitting to observed draws.
    """
    pool_arr = np.asarray(pool, dtype=np.int64)
    if pool_arr.ndim == 1:
        pool_arr = pool_arr.reshape(1, -1)
    targets = uniform_outcomes(game, n_samples=n_samples, seed=seed)
    hits = _covered_count(targets, pool_arr, tolerance, chunk=chunk)
    low, high = wilson_interval(hits, n_samples)
    return CoverageEstimate(
        coverage=hits / n_samples,
        n_samples=n_samples,
        n_tickets=int(pool_arr.shape[0]),
        tolerance=tolerance,
        ci_low=low,
        ci_high=high,
        source="monte_carlo_uniform",
        seed=seed,
    )


def empirical_coverage(
    draws: np.ndarray,
    pool: np.ndarray | list[tuple[int, ...]],
    *,
    tolerance: int = 1,
    chunk: int = 512,
) -> CoverageEstimate:
    """Coverage of ``pool`` on observed draws.

    Only meaningful when ``draws`` were sealed away from pool construction. If the pool
    was selected against these same rows, the figure is a fit statistic, not an estimate.
    """
    targets = np.asarray(draws, dtype=np.int64)
    pool_arr = np.asarray(pool, dtype=np.int64)
    if pool_arr.ndim == 1:
        pool_arr = pool_arr.reshape(1, -1)
    n = int(targets.shape[0])
    hits = _covered_count(targets, pool_arr, tolerance, chunk=chunk)
    low, high = wilson_interval(hits, n)
    return CoverageEstimate(
        coverage=hits / n if n else 0.0,
        n_samples=n,
        n_tickets=int(pool_arr.shape[0]),
        tolerance=tolerance,
        ci_low=low,
        ci_high=high,
        source="empirical_draws",
    )


def per_draw_hits(
    draws: np.ndarray,
    pool: np.ndarray | list[tuple[int, ...]],
    *,
    tolerance: int = 1,
    chunk: int = 512,
) -> np.ndarray:
    """Boolean vector of per-draw coverage. Needed for paired testing against Arm A."""
    targets = np.asarray(draws, dtype=np.int64)
    pool_arr = np.asarray(pool, dtype=np.int64)
    if pool_arr.ndim == 1:
        pool_arr = pool_arr.reshape(1, -1)
    covered = np.zeros(targets.shape[0], dtype=bool)
    if pool_arr.size == 0 or targets.size == 0:
        return covered
    for start in range(0, pool_arr.shape[0], chunk):
        block = pool_arr[start : start + chunk]
        diff = np.abs(targets[None, :, :] - block[:, None, :])
        covered |= (diff.max(axis=2) <= tolerance).any(axis=0)
    return covered
