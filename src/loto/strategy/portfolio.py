"""Coverage-aware ticket portfolio optimization with explicit popularity risk.

The optimizer does not change draw win probability. It trades model-free coverage against a
conservative co-winner-risk score supplied by a separately evaluated popularity model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from loto.combinatorics.set_cover import SolverUnavailable, incidence_matrix
from loto.game.geometry import GameGeometry


@dataclass(frozen=True)
class PortfolioResult:
    selected_indices: tuple[int, ...]
    tickets: tuple[tuple[int, ...], ...]
    coverage: float
    mean_q95_co_winner_risk: float
    max_pair_overlap_fraction: float
    budget: int
    tolerance: int
    method: str
    objective_value: float
    optimality_gap: float | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["selected_indices"] = list(self.selected_indices)
        payload["tickets"] = [list(ticket) for ticket in self.tickets]
        return payload


def _validated_candidates(
    candidates: Sequence[Sequence[int]], geometry: GameGeometry
) -> tuple[tuple[int, ...], ...]:
    normalized: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for candidate in candidates:
        values = tuple(int(value) for value in candidate)
        geometry.validate_outcome(list(values))
        if values in seen:
            raise ValueError(f"duplicate candidate ticket: {values}")
        seen.add(values)
        normalized.append(values)
    if not normalized:
        raise ValueError("candidates must be non-empty")
    return tuple(normalized)


def _risk_vector(risks: Sequence[float], n_candidates: int) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(risks, dtype=float).ravel()
    if values.size != n_candidates:
        raise ValueError("q95 co-winner risks must align with candidate tickets")
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("q95 co-winner risks must be finite and non-negative")
    spread = float(values.max() - values.min()) if len(values) else 0.0
    normalized = np.zeros_like(values) if spread <= 1e-12 else (values - values.min()) / spread
    return values, normalized


def _overlap_fraction(first: Sequence[int], second: Sequence[int], geometry: GameGeometry) -> float:
    if geometry.family == "select":
        return len(set(first) & set(second)) / geometry.positions
    return float(np.mean(np.asarray(first) == np.asarray(second)))


def _result(
    selected: list[int],
    candidates: tuple[tuple[int, ...], ...],
    risks: np.ndarray,
    masks: np.ndarray,
    geometry: GameGeometry,
    *,
    budget: int,
    tolerance: int,
    method: str,
    objective_value: float,
    optimality_gap: float | None = None,
) -> PortfolioResult:
    if selected:
        covered = masks[selected].any(axis=0)
        coverage = float(covered.mean()) if covered.size else 0.0
        mean_risk = float(risks[selected].mean())
    else:
        coverage = 0.0
        mean_risk = 0.0
    max_overlap = 0.0
    for position, first_index in enumerate(selected):
        for second_index in selected[position + 1 :]:
            max_overlap = max(
                max_overlap,
                _overlap_fraction(candidates[first_index], candidates[second_index], geometry),
            )
    return PortfolioResult(
        selected_indices=tuple(selected),
        tickets=tuple(candidates[index] for index in selected),
        coverage=coverage,
        mean_q95_co_winner_risk=mean_risk,
        max_pair_overlap_fraction=max_overlap,
        budget=budget,
        tolerance=tolerance,
        method=method,
        objective_value=float(objective_value),
        optimality_gap=optimality_gap,
    )


def optimize_portfolio_greedy(
    targets: np.ndarray,
    candidates: Sequence[Sequence[int]],
    q95_co_winner_risks: Sequence[float],
    geometry: GameGeometry,
    *,
    budget: int,
    tolerance: int = 1,
    popularity_weight: float = 0.10,
    overlap_weight: float = 0.05,
) -> PortfolioResult:
    """Deterministic multi-objective greedy portfolio.

    At each step the marginal score is:

    ``new_coverage_fraction - popularity_weight * normalized_q95_risk
       - overlap_weight * maximum_overlap_with_selected``.

    The risk normalization is confined to the supplied candidate set and is therefore part of the
    result-affecting protocol identity.
    """
    if budget < 1:
        raise ValueError("budget must be >= 1")
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    if popularity_weight < 0 or overlap_weight < 0:
        raise ValueError("objective weights must be non-negative")
    pool = _validated_candidates(candidates, geometry)
    risks, normalized_risk = _risk_vector(q95_co_winner_risks, len(pool))
    target_array = np.asarray(targets, dtype=int)
    if target_array.ndim != 2 or target_array.shape[1] != geometry.positions:
        raise ValueError(f"targets must have shape (n,{geometry.positions})")
    for row in target_array:
        geometry.validate_outcome(row.tolist())
    masks = incidence_matrix(target_array, pool, tolerance)
    uncovered = np.ones(len(target_array), dtype=bool)
    selected: list[int] = []
    total_objective = 0.0
    for _ in range(min(budget, len(pool))):
        best: tuple[float, int] | None = None
        for index, ticket in enumerate(pool):
            if index in selected:
                continue
            gain = float(masks[index, uncovered].sum() / max(len(target_array), 1))
            overlap = max(
                (_overlap_fraction(ticket, pool[other], geometry) for other in selected),
                default=0.0,
            )
            score = gain - popularity_weight * float(normalized_risk[index]) - overlap_weight * overlap
            candidate = (score, -index)
            if best is None or candidate > (best[0], -best[1]):
                best = (score, index)
        if best is None:
            break
        score, index = best
        selected.append(index)
        uncovered &= ~masks[index]
        total_objective += score
    return _result(
        selected,
        pool,
        risks,
        masks,
        geometry,
        budget=budget,
        tolerance=tolerance,
        method="greedy-popularity-coverage-v1",
        objective_value=total_objective,
    )


def optimize_portfolio_cpsat(
    targets: np.ndarray,
    candidates: Sequence[Sequence[int]],
    q95_co_winner_risks: Sequence[float],
    geometry: GameGeometry,
    *,
    budget: int,
    tolerance: int = 1,
    popularity_weight: float = 0.10,
    time_limit_seconds: float = 60.0,
    workers: int = 8,
) -> PortfolioResult:
    """Optional CP-SAT optimization of coverage minus normalized q95 popularity risk.

    Pairwise overlap is reported but deliberately excluded from the v1 exact objective so the
    solver contract stays small and auditable. Use the greedy method when overlap is a required
    optimization term.
    """
    try:  # pragma: no cover - optional dependency
        from ortools.sat.python import cp_model
    except ImportError as exc:  # pragma: no cover
        raise SolverUnavailable("ortools.cp_sat", str(exc)) from exc
    if budget < 1:
        raise ValueError("budget must be >= 1")
    if popularity_weight < 0:
        raise ValueError("popularity_weight must be non-negative")
    pool = _validated_candidates(candidates, geometry)
    risks, normalized_risk = _risk_vector(q95_co_winner_risks, len(pool))
    target_array = np.asarray(targets, dtype=int)
    if target_array.ndim != 2 or target_array.shape[1] != geometry.positions:
        raise ValueError(f"targets must have shape (n,{geometry.positions})")
    for row in target_array:
        geometry.validate_outcome(row.tolist())
    masks = incidence_matrix(target_array, pool, tolerance)
    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"ticket_{index}") for index in range(len(pool))]
    z = [model.NewBoolVar(f"covered_{index}") for index in range(len(target_array))]
    model.Add(sum(x) <= min(budget, len(pool)))
    for target_index in range(len(target_array)):
        covering = [x[index] for index in range(len(pool)) if masks[index, target_index]]
        if covering:
            model.AddMaxEquality(z[target_index], covering)
        else:
            model.Add(z[target_index] == 0)

    scale = 1_000_000
    risk_penalties = [int(round(popularity_weight * float(value) * scale)) for value in normalized_risk]
    # One covered target is worth SCALE. Popularity risk is in the same configured normalized
    # unit per selected ticket; changing this scaling changes no relative objective coefficient.
    model.Maximize(scale * sum(z) - sum(risk_penalties[index] * x[index] for index in range(len(pool))))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = int(workers)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SolverUnavailable("ortools.cp_sat", f"no feasible portfolio ({solver.StatusName(status)})")
    selected = [index for index in range(len(pool)) if solver.Value(x[index])]
    objective = float(solver.ObjectiveValue() / scale)
    gap = None
    bound = float(solver.BestObjectiveBound())
    if abs(objective) > 1e-12:
        gap = abs(bound - solver.ObjectiveValue()) / max(abs(solver.ObjectiveValue()), 1.0)
    return _result(
        selected,
        pool,
        risks,
        masks,
        geometry,
        budget=budget,
        tolerance=tolerance,
        method=f"cpsat-popularity-coverage-v1:{solver.StatusName(status)}",
        objective_value=objective,
        optimality_gap=gap,
    )
