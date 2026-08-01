"""Model-free ticket pool constructions -- the reference arm (Arm A).

Under the uniform i.i.d. draw model, every outcome is equally likely, so the *only* thing
a pool can be optimised for is geometric packing: place ticket neighbourhoods so they
overlap as little as possible while covering as much of the outcome space as possible.
That is a covering-code construction and it uses no historical data whatsoever.

This matters for the KPI. A pool built here has, by construction, zero opportunity to
leak information from the draws it is scored against. If a model-driven pool (Arm B)
cannot beat these constructions at equal ticket count on sealed draws, the correct
conclusion is that the model contributes nothing -- not that more search is needed.

Constructions
-------------
lattice
    Values placed on a grid of spacing ``2*tolerance+1``. Each ticket owns a disjoint
    cell product, giving near-zero overlap and the best efficiency per ticket. Only
    covers outcomes whose values fall in distinct cells.
offset lattice
    The lattice translated by every residue offset, which reaches outcomes the base
    lattice misses.
multiplicity augmentation
    Extra tickets for outcomes with two or more values inside one cell -- the case a pure
    lattice provably cannot cover.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from loto.game.geometry import GameGeometry, geometry_for

__all__ = [
    "DEFAULT_CONSTRUCTION",
    "greedy_uniform_pool",
    "PoolSpec",
    "lattice_pool",
    "offset_lattice_pool",
    "multiplicity_augmented_pool",
    "random_legal_pool",
    "reference_pool",
    "REFERENCE_CONSTRUCTIONS",
]


@dataclass(frozen=True)
class PoolSpec:
    """Reproducible description of how a pool was built."""

    game: str
    construction: str
    tolerance: int
    n_tickets: int
    seed: int | None = None
    parameters: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "game": self.game,
            "construction": self.construction,
            "tolerance": self.tolerance,
            "n_tickets": self.n_tickets,
            "seed": self.seed,
            "parameters": dict(self.parameters),
        }


def _legal(geometry: GameGeometry, values: Sequence[int]) -> bool:
    return geometry.is_legal(list(values))


def _cell_centres(geometry: GameGeometry, tolerance: int, offset: int) -> list[int]:
    """Representative values, spaced ``2*tolerance+1`` apart, starting at ``offset``."""
    span = 2 * tolerance + 1
    start = geometry.value_min + offset + tolerance
    centres = []
    value = start
    while value <= geometry.value_max:
        centres.append(min(value, geometry.value_max))
        value += span
    if not centres:
        centres = [geometry.value_min]
    return centres


def lattice_pool(
    game: str, *, tolerance: int = 1, limit: int | None = None, offset: int = 0
) -> tuple[list[tuple[int, ...]], PoolSpec]:
    """Tickets whose values sit on cell centres, in combination order.

    Deterministic and data-free. Enumeration is lazy and truncated at ``limit`` so this
    is safe to call on bingo5 (7.69e7 outcomes) without exhausting memory.
    """
    geometry = geometry_for(game)
    centres = _cell_centres(geometry, tolerance, offset)
    pool: list[tuple[int, ...]] = []
    if geometry.family == "select":
        source: Iterator[tuple[int, ...]] = itertools.combinations(centres, geometry.positions)
    else:
        source = itertools.product(centres, repeat=geometry.positions)
    for candidate in source:
        if _legal(geometry, candidate):
            pool.append(tuple(candidate))
            if limit is not None and len(pool) >= limit:
                break
    spec = PoolSpec(
        game=geometry.key,
        construction="lattice",
        tolerance=tolerance,
        n_tickets=len(pool),
        parameters={"offset": offset, "n_cells": len(centres), "limit": limit},
    )
    return pool, spec


def offset_lattice_pool(
    game: str, *, tolerance: int = 1, limit: int, max_offsets: int | None = None
) -> tuple[list[tuple[int, ...]], PoolSpec]:
    """Interleave lattices at every residue offset until ``limit`` tickets are produced.

    Round-robin across offsets rather than exhausting one offset first, so a truncated
    pool still spans the whole outcome space instead of clustering in one corner.
    """
    geometry = geometry_for(game)
    span = 2 * tolerance + 1
    n_offsets = span if max_offsets is None else min(span, max_offsets)
    per_offset = [
        lattice_pool(game, tolerance=tolerance, limit=limit, offset=off)[0]
        for off in range(n_offsets)
    ]
    pool: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for row in itertools.zip_longest(*per_offset):
        for ticket in row:
            if ticket is None or ticket in seen:
                continue
            seen.add(ticket)
            pool.append(ticket)
            if len(pool) >= limit:
                break
        if len(pool) >= limit:
            break
    spec = PoolSpec(
        game=geometry.key,
        construction="offset_lattice",
        tolerance=tolerance,
        n_tickets=len(pool),
        parameters={"n_offsets": n_offsets, "limit": limit},
    )
    return pool, spec


def multiplicity_augmented_pool(
    game: str, *, tolerance: int = 1, limit: int, seed: int = 42
) -> tuple[list[tuple[int, ...]], PoolSpec]:
    """Offset lattice plus tickets carrying adjacent value clusters.

    A pure lattice ticket has one value per cell, so it can never cover an outcome with
    two values inside the same cell (e.g. a draw containing both 14 and 15 at
    ``tolerance=1``). Real draws contain such clusters often, so those outcomes need
    tickets with adjacent values. This construction reserves part of the budget for them,
    in proportion to how much of the outcome space they represent.
    """
    geometry = geometry_for(game)
    if geometry.family == "digits":
        # digit games allow repetition, so the lattice already covers everything
        pool, _ = offset_lattice_pool(game, tolerance=tolerance, limit=limit)
        spec = PoolSpec(
            game=geometry.key,
            construction="multiplicity_augmented",
            tolerance=tolerance,
            n_tickets=len(pool),
            seed=seed,
            parameters={"clustered_fraction": 0.0, "reason": "digits allow repetition"},
        )
        return pool, spec

    rng = random.Random(seed)
    span = 2 * tolerance + 1
    base_share = 0.6
    base_limit = max(1, int(limit * base_share))
    pool, _ = offset_lattice_pool(game, tolerance=tolerance, limit=base_limit)
    seen = set(pool)

    # clustered tickets: pick a spread skeleton, then collapse one gap to adjacency
    guard = 0
    while len(pool) < limit and guard < limit * 200:
        guard += 1
        n_clusters = rng.randint(1, max(1, geometry.positions // 2))
        values: list[int] = []
        cursor = rng.randint(geometry.value_min, geometry.value_min + span)
        remaining = geometry.positions
        clusters_left = n_clusters
        while remaining > 0 and cursor <= geometry.value_max:
            if clusters_left > 0 and remaining >= 2 and rng.random() < 0.5:
                values.extend([cursor, cursor + 1])
                cursor += 2 + rng.randint(0, span)
                remaining -= 2
                clusters_left -= 1
            else:
                values.append(cursor)
                cursor += span + rng.randint(0, 1)
                remaining -= 1
        if len(values) != geometry.positions:
            continue
        ticket = tuple(sorted(values))
        if ticket in seen or not _legal(geometry, ticket):
            continue
        seen.add(ticket)
        pool.append(ticket)

    spec = PoolSpec(
        game=geometry.key,
        construction="multiplicity_augmented",
        tolerance=tolerance,
        n_tickets=len(pool),
        seed=seed,
        parameters={"base_share": base_share, "limit": limit, "attempts": guard},
    )
    return pool, spec


def random_legal_pool(
    game: str, *, n_tickets: int, seed: int = 42
) -> tuple[list[tuple[int, ...]], PoolSpec]:
    """Uniform random legal tickets -- the null construction.

    Included so every report can state what a pool with *no* design at all achieves.
    """
    geometry = geometry_for(game)
    rng = random.Random(seed)
    seen: set[tuple[int, ...]] = set()
    pool: list[tuple[int, ...]] = []
    guard = 0
    while len(pool) < n_tickets and guard < n_tickets * 500:
        guard += 1
        if geometry.family == "select":
            ticket = tuple(sorted(rng.sample(list(geometry.values), geometry.positions)))
        else:
            ticket = tuple(rng.choice(list(geometry.values)) for _ in range(geometry.positions))
        if ticket in seen:
            continue
        seen.add(ticket)
        pool.append(ticket)
    spec = PoolSpec(
        game=geometry.key,
        construction="random_legal",
        tolerance=0,
        n_tickets=len(pool),
        seed=seed,
        parameters={"requested": n_tickets, "attempts": guard},
    )
    return pool, spec


def greedy_uniform_pool(
    game: str,
    *,
    n_tickets: int,
    tolerance: int = 1,
    candidate_multiplier: int = 6,
    n_targets: int = 3000,
    seed: int = 42,
) -> tuple[list[tuple[int, ...]], PoolSpec]:
    """Greedy max-coverage against Monte-Carlo samples of the **uniform law**.

    Data-free in the sense that matters: the targets are drawn from the uniform outcome
    distribution, never from observed draws, so this pool cannot leak information from the
    draws it is later scored against.

    Measured caveat (loto7, tolerance=1, 2000 tickets, n_targets=3000): efficiency 0.628,
    which is *worse* than the plain ``offset_lattice`` at 0.734. Greedy carries the
    ``(1 - 1/e)`` guarantee only against the target sample it optimises, and with
    ``n_targets`` of the same order as ``n_tickets`` it overfits that sample. Being
    overfitting-proof with respect to *draws* does not make it overfitting-proof with
    respect to its own Monte-Carlo sample. Use ``n_targets >> n_tickets`` (empirically
    10x or more) or prefer ``offset_lattice``.

    Cost is ``O(candidate_multiplier * n_tickets * n_targets)`` incidence entries and runs
    in minutes at 2000 tickets, so raising ``n_targets`` is not free.
    """
    from loto.combinatorics.estimate import uniform_outcomes
    from loto.combinatorics.set_cover import greedy_max_coverage

    geometry = geometry_for(game)
    candidate_budget = max(n_tickets * candidate_multiplier, n_tickets + 1)
    lattice, _ = offset_lattice_pool(game, tolerance=tolerance, limit=candidate_budget)
    extra, _ = random_legal_pool(game, n_tickets=max(0, candidate_budget - len(lattice)), seed=seed)
    candidates = list(dict.fromkeys(lattice + extra))
    targets = uniform_outcomes(game, n_samples=n_targets, seed=seed + 1)
    result = greedy_max_coverage(
        targets, candidates, budget=n_tickets, tolerance=tolerance, record_trace=False
    )
    pool = list(result.tickets)
    if len(pool) < n_tickets:
        for ticket in candidates:
            if ticket not in set(pool):
                pool.append(ticket)
            if len(pool) >= n_tickets:
                break
    spec = PoolSpec(
        game=geometry.key,
        construction="greedy_uniform",
        tolerance=tolerance,
        n_tickets=len(pool),
        seed=seed,
        parameters={
            "candidate_pool": len(candidates),
            "n_targets": n_targets,
            "greedy_coverage_on_targets": result.coverage,
            "target_source": "uniform_monte_carlo",
        },
    )
    return pool[:n_tickets], spec


#: Registry of data-free constructions available to Arm A.
#:
#: Measured efficiency against the packing bound. loto7, tolerance=1, 2000 tickets,
#: Monte-Carlo coverage on 4000-6000 uniform samples:
#:
#:   offset_lattice          coverage 0.3118  efficiency 0.734
#:   greedy_uniform          coverage 0.2667  efficiency 0.628  (n_targets=3000)
#:   multiplicity_augmented  coverage 0.2072  efficiency 0.488
#:   random_legal            coverage 0.1945  efficiency 0.458
#:
#: Two results here are negative and are kept rather than hidden. ``multiplicity_augmented``
#: is worse than random: it spends budget on adjacent-value clusters whose share of the
#: outcome space does not justify the cost. ``greedy_uniform`` is worse than the plain
#: lattice at these settings because greedy overfits its own target sample when
#: ``n_targets`` is not far larger than ``n_tickets``.
#:
#: Reproduce with ``loto-lab bounds --game loto7`` and
#: ``tests/test_kpi_lab_minimal.py::test_reference_constructions_ranking``.
REFERENCE_CONSTRUCTIONS: dict[str, str] = {
    "offset_lattice": "lattice interleaved over all residue offsets (best measured)",
    "greedy_uniform": "greedy max-coverage vs uniform Monte-Carlo targets",
    "lattice": "cell-centre lattice, single offset",
    "multiplicity_augmented": "offset lattice plus cluster tickets (measured: weak)",
    "random_legal": "uniform random legal tickets (null construction)",
}

#: Default Arm A construction. Chosen by measured efficiency, not by preference.
DEFAULT_CONSTRUCTION = "offset_lattice"


def reference_pool(
    game: str,
    *,
    n_tickets: int,
    construction: str = DEFAULT_CONSTRUCTION,
    tolerance: int = 1,
    seed: int = 42,
) -> tuple[list[tuple[int, ...]], PoolSpec]:
    """Build an Arm A pool by name. Unknown names raise rather than defaulting."""
    if construction not in REFERENCE_CONSTRUCTIONS:
        raise ValueError(
            f"unknown construction {construction!r}; available={sorted(REFERENCE_CONSTRUCTIONS)}"
        )
    if construction == "greedy_uniform":
        return greedy_uniform_pool(game, n_tickets=n_tickets, tolerance=tolerance, seed=seed)
    if construction == "lattice":
        return lattice_pool(game, tolerance=tolerance, limit=n_tickets)
    if construction == "offset_lattice":
        return offset_lattice_pool(game, tolerance=tolerance, limit=n_tickets)
    if construction == "random_legal":
        return random_legal_pool(game, n_tickets=n_tickets, seed=seed)
    return multiplicity_augmented_pool(game, tolerance=tolerance, limit=n_tickets, seed=seed)
