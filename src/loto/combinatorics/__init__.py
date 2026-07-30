"""Combinatorial optimisation layer: the model-free reference for coverage KPIs.

Under a uniform i.i.d. draw law, maximising L-infinity coverage per ticket is a covering
code problem. This package computes the model-independent bounds, builds data-free
reference pools, and estimates coverage in a way that cannot be overfitted -- everything
Arm A of the KPI Lab needs.

Entry points
------------
:mod:`loto.combinatorics.bounds`
    Lower bounds on ticket count that no model can beat.
:mod:`loto.combinatorics.designs`
    Data-free pool constructions (lattice, offset lattice, multiplicity augmented).
:mod:`loto.combinatorics.set_cover`
    Greedy and optional exact solvers, with optimality certificates.
:mod:`loto.combinatorics.estimate`
    Monte-Carlo and empirical coverage with confidence intervals.
"""

from __future__ import annotations

from loto.combinatorics.bounds import (
    DEFAULT_UNIT_PRICE_JPY,
    FeasibilityBound,
    feasibility_bound,
    feasibility_table,
    max_neighbourhood_size,
    mean_neighbourhood_size,
    neighbourhood_size,
    packing_bound,
)
from loto.combinatorics.designs import (
    DEFAULT_CONSTRUCTION,
    REFERENCE_CONSTRUCTIONS,
    PoolSpec,
    greedy_uniform_pool,
    lattice_pool,
    multiplicity_augmented_pool,
    offset_lattice_pool,
    random_legal_pool,
    reference_pool,
)
from loto.combinatorics.estimate import (
    CoverageEstimate,
    empirical_coverage,
    monte_carlo_coverage,
    per_draw_hits,
    uniform_outcomes,
    wilson_interval,
)
from loto.combinatorics.set_cover import (
    CoverResult,
    SolverUnavailable,
    coverage_mask,
    exact_min_cover_cpsat,
    greedy_max_coverage,
    greedy_min_cover,
    incidence_matrix,
    lp_lower_bound_on_sample,
)

__all__ = [
    "DEFAULT_UNIT_PRICE_JPY",
    "DEFAULT_CONSTRUCTION",
    "REFERENCE_CONSTRUCTIONS",
    "greedy_uniform_pool",
    "CoverResult",
    "CoverageEstimate",
    "FeasibilityBound",
    "PoolSpec",
    "SolverUnavailable",
    "coverage_mask",
    "empirical_coverage",
    "exact_min_cover_cpsat",
    "feasibility_bound",
    "feasibility_table",
    "greedy_max_coverage",
    "greedy_min_cover",
    "incidence_matrix",
    "lattice_pool",
    "lp_lower_bound_on_sample",
    "max_neighbourhood_size",
    "mean_neighbourhood_size",
    "monte_carlo_coverage",
    "multiplicity_augmented_pool",
    "neighbourhood_size",
    "offset_lattice_pool",
    "packing_bound",
    "per_draw_hits",
    "random_legal_pool",
    "reference_pool",
    "uniform_outcomes",
    "wilson_interval",
]
