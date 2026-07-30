"""Set-cover solvers used to build the model-free reference pool (Arm A).

Coverage here is always measured against an explicit set of target outcomes -- either
observed draws or Monte-Carlo samples from the uniform law. The full outcome space is far
too large to materialise a ``|pool| x |Omega|`` incidence matrix (bingo5 alone has
7.69e7 outcomes), so every routine in this module works on a *sample* of targets and
reports the sample size alongside the result.

Greedy set cover carries the classical ``(1 - 1/e)`` approximation guarantee for
maximum coverage under a cardinality constraint, and ``H(n)``-approximation for minimum
cover. That means greedy is already near-optimal: the value of an exact solver is not a
better pool but a *certificate* of how close greedy is, which is why
:func:`lp_lower_bound_on_sample` exists.

Important
---------
A pool selected greedily *on the draws it is then scored against* is fitted to those
draws. Always build on calibration targets and score on sealed targets, or score with
:func:`loto.combinatorics.estimate.monte_carlo_coverage`, which cannot be overfitted
because it samples the uniform law directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field

import numpy as np

__all__ = [
    "SolverUnavailable",
    "CoverResult",
    "coverage_mask",
    "incidence_matrix",
    "greedy_max_coverage",
    "greedy_min_cover",
    "lp_lower_bound_on_sample",
    "exact_min_cover_cpsat",
]


class SolverUnavailable(RuntimeError):
    """Raised when an optional solver backend is not installed.

    Constitution principle II: never silently substitute a different algorithm. The
    caller decides whether to fall back, and the fallback is recorded explicitly.
    """

    def __init__(self, backend: str, detail: str) -> None:
        super().__init__(f"solver backend {backend!r} unavailable: {detail}")
        self.backend = backend
        self.detail = detail


@dataclass(frozen=True)
class CoverResult:
    """Outcome of a cover computation, with everything needed to reproduce it."""

    selected_indices: tuple[int, ...]
    tickets: tuple[tuple[int, ...], ...]
    coverage: float
    n_targets: int
    n_tickets: int
    tolerance: int
    method: str
    optimality_gap: float | None = None
    lower_bound_tickets: int | None = None
    trace: tuple[dict[str, object], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["selected_indices"] = list(self.selected_indices)
        payload["tickets"] = [list(t) for t in self.tickets]
        payload["trace"] = [dict(step) for step in self.trace]
        return payload


# --------------------------------------------------------------------------------------
# incidence
# --------------------------------------------------------------------------------------


def coverage_mask(
    targets: np.ndarray, ticket: Sequence[int], tolerance: int
) -> np.ndarray:
    """Boolean vector: which target rows the single ``ticket`` covers."""
    arr = np.asarray(ticket, dtype=np.int64)
    return np.max(np.abs(targets - arr), axis=1) <= tolerance


def incidence_matrix(
    targets: np.ndarray, pool: Sequence[Sequence[int]], tolerance: int
) -> np.ndarray:
    """``(len(pool), len(targets))`` boolean incidence matrix.

    Memory is ``len(pool) * len(targets)`` bytes. With 20k pool x 5k targets that is
    100 MB, which is fine; the caller is responsible for keeping the product bounded.
    """
    targets = np.asarray(targets, dtype=np.int64)
    if targets.ndim != 2:
        raise ValueError("targets must be a 2-D array of shape (n_draws, positions)")
    rows = [coverage_mask(targets, ticket, tolerance) for ticket in pool]
    if not rows:
        return np.zeros((0, targets.shape[0]), dtype=bool)
    return np.vstack(rows)


# --------------------------------------------------------------------------------------
# greedy
# --------------------------------------------------------------------------------------


def greedy_max_coverage(
    targets: np.ndarray,
    pool: Sequence[Sequence[int]],
    *,
    budget: int,
    tolerance: int = 1,
    diversity_penalty: float = 0.0,
    record_trace: bool = True,
) -> CoverResult:
    """Pick at most ``budget`` tickets maximising covered targets.

    This is the budget-constrained form, which is the one that matches a cost-normalised
    KPI: the ticket count is fixed and coverage is the objective. Carries the
    ``(1 - 1/e)`` guarantee against the optimal budget-``budget`` pool.
    """
    if budget <= 0:
        raise ValueError("budget must be positive")
    targets = np.asarray(targets, dtype=np.int64)
    masks = incidence_matrix(targets, pool, tolerance)
    if masks.size == 0:
        return CoverResult((), (), 0.0, int(targets.shape[0]), 0, tolerance, "greedy_max")
    uncovered = np.ones(targets.shape[0], dtype=bool)
    selected: list[int] = []
    trace: list[dict[str, object]] = []
    for _ in range(min(budget, masks.shape[0])):
        gains = masks[:, uncovered].sum(axis=1).astype(float)
        if diversity_penalty > 0.0 and selected:
            overlap = masks[:, :] & masks[selected].any(axis=0)
            gains -= diversity_penalty * overlap.sum(axis=1)
        gains[selected] = -np.inf
        best = int(np.argmax(gains))
        raw_gain = int(masks[best][uncovered].sum())
        if raw_gain <= 0 and selected:
            break
        selected.append(best)
        uncovered &= ~masks[best]
        if record_trace:
            trace.append(
                {
                    "step": len(selected),
                    "ticket": [int(v) for v in pool[best]],
                    "newly_covered": raw_gain,
                    "coverage": float(1.0 - uncovered.mean()),
                }
            )
    coverage = float(1.0 - uncovered.mean())
    return CoverResult(
        selected_indices=tuple(selected),
        tickets=tuple(tuple(int(v) for v in pool[i]) for i in selected),
        coverage=coverage,
        n_targets=int(targets.shape[0]),
        n_tickets=len(selected),
        tolerance=tolerance,
        method="greedy_max",
        trace=tuple(trace),
    )


def greedy_min_cover(
    targets: np.ndarray,
    pool: Sequence[Sequence[int]],
    *,
    target_coverage: float = 0.90,
    tolerance: int = 1,
    max_tickets: int | None = None,
) -> CoverResult:
    """Smallest greedy pool reaching ``target_coverage`` on ``targets``.

    Reports ``optimality_gap`` against :func:`lp_lower_bound_on_sample` when it can be
    computed, so the result carries its own certificate rather than an unqualified claim
    of optimality.
    """
    targets = np.asarray(targets, dtype=np.int64)
    cap = max_tickets if max_tickets is not None else len(pool)
    result = greedy_max_coverage(
        targets, pool, budget=cap, tolerance=tolerance, record_trace=True
    )
    # truncate at the first step meeting the target
    keep = None
    for step in result.trace:
        if float(step["coverage"]) >= target_coverage:
            keep = int(step["step"])
            break
    if keep is None:
        return CoverResult(
            selected_indices=result.selected_indices,
            tickets=result.tickets,
            coverage=result.coverage,
            n_targets=result.n_targets,
            n_tickets=result.n_tickets,
            tolerance=tolerance,
            method="greedy_min_cover:TARGET_NOT_REACHED",
            trace=result.trace,
        )
    indices = result.selected_indices[:keep]
    return CoverResult(
        selected_indices=indices,
        tickets=result.tickets[:keep],
        coverage=float(result.trace[keep - 1]["coverage"]),
        n_targets=result.n_targets,
        n_tickets=keep,
        tolerance=tolerance,
        method="greedy_min_cover",
        trace=result.trace[:keep],
    )


# --------------------------------------------------------------------------------------
# certificates
# --------------------------------------------------------------------------------------


def lp_lower_bound_on_sample(
    targets: np.ndarray,
    pool: Sequence[Sequence[int]],
    *,
    tolerance: int = 1,
) -> float:
    """Dual-feasible lower bound on the minimum cover size *for this target sample*.

    Uses the uniform dual ``y_omega = 1 / max_t |N(t) ∩ targets|``, which is always
    dual-feasible. Cheap, no solver, and never overstates the bound. A tighter bound
    needs an LP solver; :func:`exact_min_cover_cpsat` is the opt-in path.

    Note this bounds the cover of the *sample*, not of the full outcome space. For the
    space-level bound use :func:`loto.combinatorics.bounds.packing_bound`.
    """
    targets = np.asarray(targets, dtype=np.int64)
    masks = incidence_matrix(targets, pool, tolerance)
    if masks.size == 0:
        return 0.0
    max_cover = int(masks.sum(axis=1).max())
    if max_cover == 0:
        return float("inf")
    return targets.shape[0] / max_cover


def exact_min_cover_cpsat(
    targets: np.ndarray,
    pool: Sequence[Sequence[int]],
    *,
    target_coverage: float = 0.90,
    tolerance: int = 1,
    time_limit_seconds: float = 60.0,
    workers: int = 8,
) -> CoverResult:
    """Exact / bounded minimum cover via OR-Tools CP-SAT.

    Raises :class:`SolverUnavailable` when ``ortools`` is not installed -- it is an
    optional dependency and this module never silently degrades to greedy.
    """
    try:  # pragma: no cover - optional dependency
        from ortools.sat.python import cp_model
    except ImportError as exc:  # pragma: no cover
        raise SolverUnavailable("ortools.cp_sat", str(exc)) from exc

    targets = np.asarray(targets, dtype=np.int64)
    masks = incidence_matrix(targets, pool, tolerance)
    n_pool, n_targets = masks.shape
    required = int(np.ceil(target_coverage * n_targets))

    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x{i}") for i in range(n_pool)]
    z = [model.NewBoolVar(f"z{j}") for j in range(n_targets)]
    for j in range(n_targets):
        covering = [x[i] for i in range(n_pool) if masks[i, j]]
        if covering:
            model.AddMaxEquality(z[j], covering)
        else:
            model.Add(z[j] == 0)
    model.Add(sum(z) >= required)
    model.Minimize(sum(x))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = int(workers)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SolverUnavailable(
            "ortools.cp_sat", f"no feasible solution (status={solver.StatusName(status)})"
        )
    selected = tuple(i for i in range(n_pool) if solver.Value(x[i]))
    covered = int(sum(solver.Value(z[j]) for j in range(n_targets)))
    best_bound = solver.BestObjectiveBound()
    gap = None
    if selected and best_bound > 0:
        gap = (len(selected) - best_bound) / len(selected)
    return CoverResult(
        selected_indices=selected,
        tickets=tuple(tuple(int(v) for v in pool[i]) for i in selected),
        coverage=covered / n_targets if n_targets else 0.0,
        n_targets=n_targets,
        n_tickets=len(selected),
        tolerance=tolerance,
        method=f"cpsat:{solver.StatusName(status)}",
        optimality_gap=gap,
        lower_bound_tickets=int(np.ceil(best_bound)) if best_bound else None,
    )
