"""The two arms the lab compares.

Arm A -- reference
    A pool built with no access to the draws it will be scored against, using the covering
    constructions in :mod:`loto.combinatorics.designs`. Under a uniform i.i.d. draw law this
    is the best a pool can do, so it is the correct null.

Arm B -- model
    A pool built from a point forecast plus a residual spread, exactly as the existing
    ``loto.coverage`` pipeline does. Any historical structure a model can find shows up here
    as coverage above Arm A.

The comparison is paired per draw at equal ticket count. Equal ticket count is not a
convenience; without it the difference measures budget rather than skill, which is the flaw
in the original ``target_coverage``-only objective.

Both arms are built on a calibration window and scored on a sealed window. Arm A ignores the
calibration window entirely, which is what makes it immune to the leakage Arm B can suffer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np

from loto.combinatorics.designs import DEFAULT_CONSTRUCTION, reference_pool
from loto.combinatorics.estimate import (
    empirical_coverage,
    monte_carlo_coverage,
    per_draw_hits,
)
from loto.combinatorics.set_cover import greedy_max_coverage
from loto.game.geometry import GameGeometry, geometry_for

__all__ = [
    "ArmId",
    "ArmResult",
    "ArmComparison",
    "build_reference_arm",
    "build_model_arm",
    "compare_arms",
    "point_forecast",
    "candidate_pool_from_forecast",
]

ArmId = Literal["A_reference", "B_model"]
_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class ArmResult:
    """A built pool with its coverage measured two independent ways."""

    arm_id: ArmId
    game: str
    construction: str
    n_tickets: int
    tolerance: int
    tickets: tuple[tuple[int, ...], ...]
    sealed_coverage: float
    sealed_ci: tuple[float, float]
    n_sealed_draws: int
    monte_carlo_coverage: float
    monte_carlo_ci: tuple[float, float]
    n_monte_carlo: int
    parameters: dict[str, Any] = field(default_factory=dict)
    calibration_coverage: float | None = None
    schema_version: str = _SCHEMA_VERSION

    @property
    def overfit_gap(self) -> float | None:
        """Calibration coverage minus sealed coverage.

        A large positive gap is the signature of a pool fitted to its build window.
        """
        if self.calibration_coverage is None:
            return None
        return self.calibration_coverage - self.sealed_coverage

    @property
    def uniformity_gap(self) -> float:
        """Sealed coverage minus Monte-Carlo coverage under the uniform law.

        Positive beyond sampling error means the pool is exploiting structure in the observed
        draws. That is either a real departure from uniformity or a leak; the control suite
        decides which.
        """
        return self.sealed_coverage - self.monte_carlo_coverage

    def to_dict(self, *, include_tickets: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        payload["sealed_ci"] = list(self.sealed_ci)
        payload["monte_carlo_ci"] = list(self.monte_carlo_ci)
        payload["overfit_gap"] = self.overfit_gap
        payload["uniformity_gap"] = self.uniformity_gap
        if include_tickets:
            payload["tickets"] = [list(t) for t in self.tickets]
        else:
            payload.pop("tickets", None)
            payload["tickets_omitted"] = True
        return payload


@dataclass(frozen=True)
class ArmComparison:
    """Paired comparison of the two arms on the same sealed draws."""

    reference: ArmResult
    model: ArmResult
    delta: float
    n_draws: int
    n_discordant: int
    model_only: int
    reference_only: int
    equal_ticket_count: bool
    model_hits: tuple[bool, ...] = field(default_factory=tuple)
    reference_hits: tuple[bool, ...] = field(default_factory=tuple)
    schema_version: str = _SCHEMA_VERSION

    def to_dict(self, *, include_hits: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reference": self.reference.to_dict(),
            "model": self.model.to_dict(),
            "delta": self.delta,
            "n_draws": self.n_draws,
            "n_discordant": self.n_discordant,
            "model_only": self.model_only,
            "reference_only": self.reference_only,
            "equal_ticket_count": self.equal_ticket_count,
            "schema_version": self.schema_version,
        }
        if include_hits:
            payload["model_hits"] = [bool(h) for h in self.model_hits]
            payload["reference_hits"] = [bool(h) for h in self.reference_hits]
        return payload


# --------------------------------------------------------------------------------------
# forecasting primitives (Arm B)
# --------------------------------------------------------------------------------------


def point_forecast(
    history: np.ndarray,
    *,
    method: str,
    window: int = 25,
    halflife: float = 10.0,
) -> np.ndarray:
    """Per-position point forecast from history. Unknown methods raise.

    Kept deliberately small: the question this lab answers is not "which forecaster is
    best" but "does any forecaster beat a data-free covering pool". A wider model set is
    reachable through :mod:`loto.models`, but it changes nothing about the comparison.
    """
    arr = np.asarray(history, dtype=float)
    if arr.ndim != 2 or arr.shape[0] == 0:
        raise ValueError("history must be a non-empty 2-D array")
    if method == "last":
        return arr[-1]
    if method == "mean":
        return arr.mean(axis=0)
    if method == "median":
        return np.median(arr, axis=0)
    if method == "rolling_mean":
        return arr[-min(window, arr.shape[0]) :].mean(axis=0)
    if method == "ewm":
        n = arr.shape[0]
        decay = np.exp(-np.log(2.0) * np.arange(n - 1, -1, -1) / max(halflife, 1e-9))
        weights = decay / decay.sum()
        return (arr * weights[:, None]).sum(axis=0)
    if method == "seasonal_naive":
        return arr[-1]
    if method == "drift":
        if arr.shape[0] < 2:
            return arr[-1]
        slope = (arr[-1] - arr[0]) / max(arr.shape[0] - 1, 1)
        return arr[-1] + slope
    raise ValueError(f"unknown point_method={method!r}")


def _legalise(values: Sequence[float], geometry: GameGeometry) -> tuple[int, ...] | None:
    """Project a real-valued vector onto the legal outcome set, or reject it."""
    lo, hi = geometry.value_min, geometry.value_max
    ints = [int(round(float(v))) for v in values]
    ints = [min(max(v, lo), hi) for v in ints]
    if geometry.family == "digits":
        return tuple(ints)
    seen: list[int] = []
    for value in sorted(ints):
        candidate = value
        while candidate in seen and candidate < hi:
            candidate += 1
        while candidate in seen and candidate > lo:
            candidate -= 1
        if candidate in seen:
            return None
        seen.append(candidate)
    seen.sort()
    return tuple(seen) if geometry.is_legal(seen) else None


def candidate_pool_from_forecast(
    centre: np.ndarray,
    residuals: np.ndarray,
    *,
    game: str,
    pool_size: int,
    per_position_top: int = 5,
    residual_scale: float = 1.0,
    seed: int = 42,
) -> list[tuple[int, ...]]:
    """Candidate tickets around ``centre``, spread by the observed residual distribution."""
    geometry = geometry_for(game)
    rng = np.random.default_rng(seed)
    pool: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()

    base = _legalise(centre, geometry)
    if base is not None:
        pool.append(base)
        seen.add(base)

    resid = np.asarray(residuals, dtype=float)
    if resid.size == 0:
        resid = np.zeros((1, geometry.positions))
    offsets = np.arange(-per_position_top, per_position_top + 1)

    guard = 0
    while len(pool) < pool_size and guard < pool_size * 50:
        guard += 1
        if rng.random() < 0.5 and resid.shape[0] > 0:
            draw = resid[rng.integers(0, resid.shape[0])] * residual_scale
        else:
            draw = rng.choice(offsets, size=geometry.positions).astype(float)
        ticket = _legalise(np.asarray(centre, dtype=float) + draw, geometry)
        if ticket is None or ticket in seen:
            continue
        seen.add(ticket)
        pool.append(ticket)
    return pool


# --------------------------------------------------------------------------------------
# arm builders
# --------------------------------------------------------------------------------------


def build_reference_arm(
    *,
    game: str,
    n_tickets: int,
    sealed_draws: np.ndarray,
    tolerance: int = 1,
    construction: str = DEFAULT_CONSTRUCTION,
    seed: int = 42,
    n_monte_carlo: int = 8000,
) -> ArmResult:
    """Arm A. Never sees ``sealed_draws`` during construction -- only during scoring."""
    tickets, spec = reference_pool(
        game,
        n_tickets=n_tickets,
        construction=construction,
        tolerance=tolerance,
        seed=seed,
    )
    sealed = empirical_coverage(sealed_draws, tickets, tolerance=tolerance)
    mc = monte_carlo_coverage(
        game, tickets, tolerance=tolerance, n_samples=n_monte_carlo, seed=seed + 3
    )
    return ArmResult(
        arm_id="A_reference",
        game=game,
        construction=construction,
        n_tickets=len(tickets),
        tolerance=tolerance,
        tickets=tuple(tickets),
        sealed_coverage=sealed.coverage,
        sealed_ci=(sealed.ci_low, sealed.ci_high),
        n_sealed_draws=sealed.n_samples,
        monte_carlo_coverage=mc.coverage,
        monte_carlo_ci=(mc.ci_low, mc.ci_high),
        n_monte_carlo=mc.n_samples,
        parameters=spec.to_dict(),
        calibration_coverage=None,
    )


def build_model_arm(
    *,
    game: str,
    n_tickets: int,
    history: np.ndarray,
    calibration_draws: np.ndarray,
    sealed_draws: np.ndarray,
    parameters: Mapping[str, Any],
    tolerance: int = 1,
    seed: int = 42,
    n_monte_carlo: int = 8000,
) -> ArmResult:
    """Arm B. Builds on ``history`` and ``calibration_draws``; scored on ``sealed_draws``."""
    geometry = geometry_for(game)
    method = str(parameters.get("point_method", "mean"))
    window = int(parameters.get("window", 25))
    halflife = float(parameters.get("halflife", 10.0))
    pool_size = int(parameters.get("pool_size", max(n_tickets * 5, 100)))
    per_position_top = int(parameters.get("per_position_top", 5))
    residual_scale = float(parameters.get("residual_scale", 1.0))
    diversity = float(parameters.get("diversity_penalty", 0.0))
    proposal_seed = int(parameters.get("proposal_seed", seed))

    centre = point_forecast(history, method=method, window=window, halflife=halflife)

    # residuals from a walk-forward over the calibration window only
    residual_rows: list[np.ndarray] = []
    cal = np.asarray(calibration_draws, dtype=float)
    hist_f = np.asarray(history, dtype=float)
    combined = np.vstack([hist_f, cal]) if cal.size else hist_f
    for idx in range(np.asarray(history).shape[0], combined.shape[0]):
        past = combined[:idx]
        if past.shape[0] < 2:
            continue
        pred = point_forecast(past, method=method, window=window, halflife=halflife)
        residual_rows.append(combined[idx] - pred)
    residuals = np.vstack(residual_rows) if residual_rows else np.zeros((1, geometry.positions))

    candidates = candidate_pool_from_forecast(
        centre,
        residuals,
        game=game,
        pool_size=max(pool_size, n_tickets),
        per_position_top=per_position_top,
        residual_scale=residual_scale,
        seed=proposal_seed,
    )

    # Select the pool against the CALIBRATION draws, never the sealed draws.
    selection_targets = (
        np.asarray(calibration_draws, dtype=np.int64)
        if np.asarray(calibration_draws).size
        else np.asarray(history[-min(50, len(history)) :], dtype=np.int64)
    )
    selected = greedy_max_coverage(
        selection_targets,
        candidates,
        budget=n_tickets,
        tolerance=tolerance,
        diversity_penalty=diversity,
        record_trace=False,
    )
    tickets = list(selected.tickets)
    if len(tickets) < n_tickets:
        for ticket in candidates:
            if ticket not in set(tickets):
                tickets.append(ticket)
            if len(tickets) >= n_tickets:
                break

    sealed = empirical_coverage(sealed_draws, tickets, tolerance=tolerance)
    mc = monte_carlo_coverage(
        game, tickets, tolerance=tolerance, n_samples=n_monte_carlo, seed=seed + 5
    )
    return ArmResult(
        arm_id="B_model",
        game=game,
        construction=f"forecast:{method}",
        n_tickets=len(tickets),
        tolerance=tolerance,
        tickets=tuple(tickets),
        sealed_coverage=sealed.coverage,
        sealed_ci=(sealed.ci_low, sealed.ci_high),
        n_sealed_draws=sealed.n_samples,
        monte_carlo_coverage=mc.coverage,
        monte_carlo_ci=(mc.ci_low, mc.ci_high),
        n_monte_carlo=mc.n_samples,
        parameters=dict(parameters),
        calibration_coverage=selected.coverage,
    )


def compare_arms(
    reference: ArmResult,
    model: ArmResult,
    sealed_draws: np.ndarray,
    *,
    tolerance: int = 1,
    keep_hits: bool = True,
) -> ArmComparison:
    """Paired per-draw comparison. Flags unequal ticket counts rather than normalising them."""
    draws = np.asarray(sealed_draws, dtype=np.int64)
    ref_hits = per_draw_hits(draws, list(reference.tickets), tolerance=tolerance)
    mod_hits = per_draw_hits(draws, list(model.tickets), tolerance=tolerance)
    model_only = int(np.sum(mod_hits & ~ref_hits))
    reference_only = int(np.sum(ref_hits & ~mod_hits))
    return ArmComparison(
        reference=reference,
        model=model,
        delta=float(mod_hits.mean() - ref_hits.mean()),
        n_draws=int(draws.shape[0]),
        n_discordant=model_only + reference_only,
        model_only=model_only,
        reference_only=reference_only,
        equal_ticket_count=reference.n_tickets == model.n_tickets,
        model_hits=tuple(bool(h) for h in mod_hits) if keep_hits else (),
        reference_hits=tuple(bool(h) for h in ref_hits) if keep_hits else (),
    )
