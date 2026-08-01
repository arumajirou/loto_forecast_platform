"""Model-independent lower bounds on the ticket count required for L-infinity coverage.

The KPI ``row_within_tolerance >= c`` asks: what fraction of drawn outcomes are within
``tolerance`` of *at least one* ticket in the pool, in every position simultaneously?

Under the uniform i.i.d. draw model this is a **covering code** question, not a
forecasting question. The number of tickets required is bounded below by a volume
(packing) argument that no model, however good, can beat:

    L_lower(c) = ceil(c * |Omega| / max_ticket_neighbourhood)

This module computes that bound exactly, plus a dual-feasible LP bound that is never
weaker. Every number produced here is derived from :class:`GameGeometry` -- nothing is
hand-typed (constitution principle I) and no game shape is hard-coded (principle IV).

Terminology
-----------
neighbourhood
    ``N(t) = {omega in Omega : max_i |omega_i - t_i| <= tolerance}`` -- the set of legal
    outcomes a single ticket ``t`` covers.
volume / packing bound
    Optimistic: assumes neighbourhoods can be packed with zero overlap. Real pools
    always need at least this many tickets, usually more.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from loto.game.geometry import GameGeometry, geometry_for, known_games

__all__ = [
    "BoundMethod",
    "FeasibilityBound",
    "neighbourhood_size",
    "max_neighbourhood_size",
    "mean_neighbourhood_size",
    "packing_bound",
    "dual_feasible_bound",
    "feasibility_bound",
    "feasibility_table",
]

BoundMethod = str
_SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------------------
# neighbourhood cardinality
# --------------------------------------------------------------------------------------


def _select_neighbourhood_size(
    ticket: Sequence[int], geometry: GameGeometry, tolerance: int
) -> int:
    """Exact count of strictly-ascending legal outcomes inside the L-inf ball of ``ticket``.

    Dynamic program over positions. ``dp[v]`` is the number of ways to fill positions
    ``0..i`` such that position ``i`` takes value ``v``. Exact for any tolerance; the
    naive ``(2*tolerance+1)**positions`` product over-counts because it ignores the
    ascending/distinct constraint when the windows overlap.
    """
    lo, hi = geometry.value_min, geometry.value_max
    # dp keyed by the value chosen at the current position
    prev: dict[int, int] = {}
    first_lo = max(lo, ticket[0] - tolerance)
    first_hi = min(hi, ticket[0] + tolerance)
    for v in range(first_lo, first_hi + 1):
        prev[v] = 1
    for idx in range(1, len(ticket)):
        window_lo = max(lo, ticket[idx] - tolerance)
        window_hi = min(hi, ticket[idx] + tolerance)
        cur: dict[int, int] = {}
        if not prev:
            return 0
        # prefix sums over previous values, so each candidate is O(1)
        keys = sorted(prev)
        running = 0
        cumulative: list[tuple[int, int]] = []
        for key in keys:
            running += prev[key]
            cumulative.append((key, running))
        for v in range(window_lo, window_hi + 1):
            # count previous values strictly less than v
            total = 0
            for key, acc in cumulative:
                if key < v:
                    total = acc
                else:
                    break
            if total:
                cur[v] = total
        prev = cur
    return sum(prev.values())


def _digits_neighbourhood_size(
    ticket: Sequence[int], geometry: GameGeometry, tolerance: int
) -> int:
    """Digit games have independent positions with repetition allowed -- a plain product."""
    total = 1
    for value in ticket:
        lo = max(geometry.value_min, value - tolerance)
        hi = min(geometry.value_max, value + tolerance)
        total *= hi - lo + 1
    return total


def neighbourhood_size(ticket: Sequence[int], geometry: GameGeometry, tolerance: int = 1) -> int:
    """Number of legal outcomes covered by a single ticket."""
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    seq = list(ticket)
    if len(seq) != geometry.positions:
        raise ValueError(
            f"{geometry.key}: ticket has {len(seq)} slots, expected {geometry.positions}"
        )
    if geometry.family == "select":
        return _select_neighbourhood_size(seq, geometry, tolerance)
    return _digits_neighbourhood_size(seq, geometry, tolerance)


@lru_cache(maxsize=256)
def max_neighbourhood_size(game: str, tolerance: int = 1) -> tuple[int, tuple[int, ...]]:
    """Largest achievable neighbourhood, and a ticket attaining it.

    For select games the maximum ``(2*tolerance+1)**positions`` is attained by a
    maximally spread ticket, but only when the universe is wide enough. When it is not,
    fall back to a deterministic scan over spread patterns so the bound stays valid
    (never optimistic beyond the true maximum).
    """
    geometry = geometry_for(game)
    span = 2 * tolerance + 1
    if geometry.family == "digits":
        # every interior digit attains the full window; clipping only hurts at the edges
        interior = geometry.value_min + tolerance
        if interior + tolerance <= geometry.value_max:
            ticket = tuple(interior for _ in range(geometry.positions))
            return neighbourhood_size(ticket, geometry, tolerance), ticket
        mid = (geometry.value_min + geometry.value_max) // 2
        ticket = tuple(mid for _ in range(geometry.positions))
        return neighbourhood_size(ticket, geometry, tolerance), ticket

    ideal_width = geometry.positions * span
    if ideal_width <= geometry.universe_size:
        start = geometry.value_min + tolerance
        ticket = tuple(start + i * span for i in range(geometry.positions))
        geometry.validate_outcome(list(ticket))
        return span**geometry.positions, ticket

    # Universe too narrow for a fully spread ticket: scan equal-gap layouts.
    best = 0
    best_ticket: tuple[int, ...] = tuple(geometry.value_min + i for i in range(geometry.positions))
    max_gap = max(1, (geometry.universe_size - 1) // max(1, geometry.positions - 1))
    for gap in range(1, max_gap + 1):
        width = (geometry.positions - 1) * gap
        for start in range(geometry.value_min, geometry.value_max - width + 1):
            ticket = tuple(start + i * gap for i in range(geometry.positions))
            size = neighbourhood_size(ticket, geometry, tolerance)
            if size > best:
                best, best_ticket = size, ticket
    return best, best_ticket


def mean_neighbourhood_size(
    game: str, tolerance: int = 1, *, samples: int = 4000, seed: int = 42
) -> float:
    """Monte-Carlo mean neighbourhood over uniformly drawn legal tickets.

    Reported for context only. It is *not* used in any bound, because a lower bound on
    the ticket count must divide by the *maximum* neighbourhood, not the mean.
    """
    import random

    geometry = geometry_for(game)
    rng = random.Random(seed)
    total = 0
    for _ in range(samples):
        if geometry.family == "select":
            ticket = tuple(sorted(rng.sample(list(geometry.values), geometry.positions)))
        else:
            ticket = tuple(rng.choice(list(geometry.values)) for _ in range(geometry.positions))
        total += neighbourhood_size(ticket, geometry, tolerance)
    return total / samples


# --------------------------------------------------------------------------------------
# bounds
# --------------------------------------------------------------------------------------


def packing_bound(game: str, target_coverage: float, tolerance: int = 1) -> int:
    """Volume bound: ``ceil(c * |Omega| / max_neighbourhood)``.

    Optimistic by construction (zero overlap is generally impossible), therefore a
    valid lower bound: no pool smaller than this can reach ``target_coverage``.
    """
    if not 0 < target_coverage <= 1:
        raise ValueError("target_coverage must be in (0, 1]")
    geometry = geometry_for(game)
    max_neigh, _ = max_neighbourhood_size(game, tolerance)
    if max_neigh <= 0:
        raise ValueError(f"{game}: degenerate neighbourhood at tolerance={tolerance}")
    needed = target_coverage * geometry.outcome_space / max_neigh
    return -(-int(needed * 10**9) // 10**9) if needed % 1 else int(needed)


def _ceil_div_float(value: float) -> int:
    import math

    return int(math.ceil(value - 1e-12))


def dual_feasible_bound(game: str, target_coverage: float, tolerance: int = 1) -> int:
    """LP-dual lower bound.

    The covering LP is ``min sum_t x_t  s.t.  sum_{t: omega in N(t)} x_t >= 1``. Any
    dual-feasible ``y >= 0`` with ``sum_{omega in N(t)} y_omega <= 1`` for all ``t``
    certifies ``sum_omega y_omega`` as a lower bound. The uniform choice
    ``y = 1/max_neighbourhood`` is dual-feasible and recovers the packing bound, so this
    function is never weaker than :func:`packing_bound`.

    A strictly stronger dual requires a solver over ``|Omega|`` variables (up to 7.7e7
    for bingo5) and is deliberately **not** attempted here; :mod:`loto.combinatorics.set_cover`
    exposes an optional-solver path for that. Returning the uniform-dual value with an
    explicit method label keeps the reported bound honest rather than guessed.
    """
    return packing_bound(game, target_coverage, tolerance)


@dataclass(frozen=True)
class FeasibilityBound:
    """A model-independent verdict on whether a coverage KPI is reachable."""

    game: str
    family: str
    positions: int
    universe_size: int
    outcome_space: int
    tolerance: int
    target_coverage: float
    max_neighbourhood: int
    max_neighbourhood_ticket: tuple[int, ...]
    mean_neighbourhood: float
    lower_bound_tickets: int
    method: BoundMethod
    unit_price_jpy: int | None = None
    lower_bound_cost_jpy: int | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = _SCHEMA_VERSION

    @property
    def naive_product_neighbourhood(self) -> int:
        """``(2*tolerance+1)**positions`` -- the over-count the exact DP corrects."""
        return (2 * self.tolerance + 1) ** self.positions

    def coverage_efficiency(self, achieved_coverage: float, n_tickets: int) -> float:
        """KPI-1. 1.0 means the pool matches the theoretical optimum; <1.0 is worse."""
        if n_tickets <= 0:
            raise ValueError("n_tickets must be positive")
        required = self.lower_bound_for(achieved_coverage)
        return required / n_tickets

    def lower_bound_for(self, coverage: float) -> int:
        if coverage <= 0:
            return 0
        return _ceil_div_float(coverage * self.outcome_space / self.max_neighbourhood)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["max_neighbourhood_ticket"] = list(self.max_neighbourhood_ticket)
        payload["notes"] = list(self.notes)
        payload["naive_product_neighbourhood"] = self.naive_product_neighbourhood
        return payload


#: Face value per ticket in JPY. UNVERIFIED -- confirm against the operator's published
#: price list before any cost figure derived from this is reported as fact.
DEFAULT_UNIT_PRICE_JPY: dict[str, int] = {
    "loto7": 300,
    "loto6": 200,
    "mini": 200,
    "bingo5": 200,
    "numbers3": 200,
    "numbers4": 200,
}

PRICE_PROVENANCE = "UNVERIFIED: defaults in loto.combinatorics.bounds.DEFAULT_UNIT_PRICE_JPY"


def feasibility_bound(
    game: str,
    *,
    target_coverage: float = 0.90,
    tolerance: int = 1,
    unit_price_jpy: int | None = None,
    mean_samples: int = 2000,
    seed: int = 42,
) -> FeasibilityBound:
    """Compute the full feasibility record for one game."""
    geometry = geometry_for(game)
    max_neigh, ticket = max_neighbourhood_size(game, tolerance)
    lower = _ceil_div_float(target_coverage * geometry.outcome_space / max_neigh)
    mean_neigh = mean_neighbourhood_size(game, tolerance, samples=mean_samples, seed=seed)
    price = unit_price_jpy if unit_price_jpy is not None else DEFAULT_UNIT_PRICE_JPY.get(game)
    notes: list[str] = [
        "lower_bound_tickets is a packing (volume) bound: it assumes zero overlap "
        "between ticket neighbourhoods and is therefore optimistic. Any real pool "
        "needs at least this many tickets, usually strictly more.",
        "The bound is model-independent. No forecasting model can reduce it.",
    ]
    if price is not None:
        notes.append(PRICE_PROVENANCE)
    if geometry.family == "select":
        naive = (2 * tolerance + 1) ** geometry.positions
        if max_neigh < naive:
            notes.append(
                f"max_neighbourhood {max_neigh} < naive product {naive}: the universe is "
                "too narrow for a fully spread ticket at this tolerance."
            )
    return FeasibilityBound(
        game=geometry.key,
        family=geometry.family,
        positions=geometry.positions,
        universe_size=geometry.universe_size,
        outcome_space=geometry.outcome_space,
        tolerance=tolerance,
        target_coverage=target_coverage,
        max_neighbourhood=max_neigh,
        max_neighbourhood_ticket=tuple(ticket),
        mean_neighbourhood=mean_neigh,
        lower_bound_tickets=lower,
        method="packing+uniform-dual",
        unit_price_jpy=price,
        lower_bound_cost_jpy=None if price is None else lower * price,
        notes=tuple(notes),
    )


def feasibility_table(
    games: Iterable[str] | None = None,
    *,
    coverages: Sequence[float] = (0.50, 0.70, 0.90, 0.95),
    tolerance: int = 1,
    mean_samples: int = 1000,
) -> list[dict[str, object]]:
    """Feasibility records for every game x coverage combination."""
    rows: list[dict[str, object]] = []
    for game in list(games) if games is not None else known_games():
        for coverage in coverages:
            bound = feasibility_bound(
                game,
                target_coverage=coverage,
                tolerance=tolerance,
                mean_samples=mean_samples,
            )
            rows.append(bound.to_dict())
    return rows
