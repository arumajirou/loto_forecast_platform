"""KPI definitions for the coverage lab, and the cost model that keeps them honest.

Why the KPI needed redefining
-----------------------------
The pre-existing target was ``row_within_tolerance >= 0.90`` with ``max_candidates=5000``
and no fixed ticket count. That objective has no denominator: it is satisfied by enlarging
the candidate pool, regardless of any model. The packing bound in
:mod:`loto.combinatorics.bounds` shows loto7 needs at least 4,237 tickets for 90% coverage
at tolerance 1 -- a bound that holds for every model, so "reaching 90%" measures budget,
not skill.

The KPIs below therefore fix the ticket count and measure two things separately:

KPI-1 ``coverage_efficiency``
    Achieved coverage relative to the theoretical optimum at the same ticket count.
    ``1.0`` is the packing bound; anything above ``1.0`` is impossible and indicates a bug
    or a leak.
KPI-2 ``arm_delta``
    Coverage of the model arm minus coverage of the model-free reference arm, at equal
    ticket count on the same sealed draws. This is the only quantity that isolates model
    contribution. ``<= 0`` means the model adds nothing.

A tolerance band is not a prize
-------------------------------
``tolerance=1`` coverage means every position landed within one of a ticket's numbers. No
Japanese number-selection lottery pays for that -- prizes require exact matches (set
overlap for select games, exact digits for digit games). So coverage is a **forecast
accuracy proxy, not a payout metric**, and a ticket-count cost figure must never be read
alongside a coverage figure as if it were a return. :class:`CostModel` enforces the
separation by refusing to derive expected return from coverage at all.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from loto.combinatorics.bounds import DEFAULT_UNIT_PRICE_JPY, feasibility_bound
from loto.game.geometry import geometry_for

__all__ = [
    "KpiDefinition",
    "KpiMeasurement",
    "CostModel",
    "CostEstimate",
    "coverage_efficiency",
    "kpi_definition_hash",
]

_SCHEMA_VERSION = "1.0.0"

Objective = Literal["coverage_efficiency", "arm_delta", "raw_coverage"]


def kpi_definition_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over the canonical KPI definition.

    Separate from ``protocol_hash`` on purpose: the evaluation protocol and the KPI being
    optimised are independent axes, and a change to either must invalidate comparisons.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def coverage_efficiency(
    *, achieved_coverage: float, n_tickets: int, lower_bound_tickets_at_coverage: int
) -> float:
    """KPI-1. Tickets theoretically required, divided by tickets actually used.

    ``1.0`` means the pool matches the packing bound. Values above ``1.0`` are impossible
    for a valid pool and must be treated as a defect, not a result.
    """
    if n_tickets <= 0:
        raise ValueError("n_tickets must be positive")
    if not 0.0 <= achieved_coverage <= 1.0:
        raise ValueError("achieved_coverage must be in [0, 1]")
    return lower_bound_tickets_at_coverage / n_tickets


@dataclass(frozen=True)
class KpiDefinition:
    """Frozen statement of what the lab is trying to achieve, and on what budget.

    ``n_tickets`` is mandatory and fixed. A lab run that is allowed to vary the ticket
    count cannot produce a comparable number, so there is deliberately no "unlimited"
    option.
    """

    game: str
    objective: Objective = "arm_delta"
    tolerance: int = 1
    n_tickets: int = 2000
    target_coverage: float = 0.90
    min_arm_delta: float = 0.0
    alpha: float = 0.01
    max_false_positive_rate: float = 0.05
    require_reference_arm: bool = True
    reference_construction: str = "offset_lattice"
    schema_version: str = _SCHEMA_VERSION
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        geometry_for(self.game)  # raises on unknown game
        if self.n_tickets <= 0:
            raise ValueError("n_tickets must be positive and fixed")
        if self.tolerance < 0:
            raise ValueError("tolerance must be non-negative")
        if not 0 < self.target_coverage <= 1:
            raise ValueError("target_coverage must be in (0, 1]")
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must be in (0, 1)")
        if not 0 <= self.max_false_positive_rate < 1:
            raise ValueError("max_false_positive_rate must be in [0, 1)")
        if self.objective == "raw_coverage" and self.require_reference_arm is False:
            object.__setattr__(
                self,
                "notes",
                tuple(self.notes)
                + (
                    "objective=raw_coverage with require_reference_arm=False produces a "
                    "number that cannot distinguish model skill from ticket budget.",
                ),
            )

    def canonical(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("notes", None)
        payload["notes_count"] = len(self.notes)
        return payload

    @property
    def hash(self) -> str:
        return kpi_definition_hash(self.canonical())

    def feasibility(self):
        """Packing bound for this KPI. Raises nothing; purely derived from geometry."""
        return feasibility_bound(
            self.game,
            target_coverage=self.target_coverage,
            tolerance=self.tolerance,
        )

    def is_degenerate(self) -> bool:
        """True when the ticket budget alone guarantees the target.

        A budget at or above the packing bound makes ``target_coverage`` reachable by
        construction, so an "achieved" verdict would say nothing about any model.
        """
        return self.n_tickets >= self.feasibility().lower_bound_tickets

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["notes"] = list(self.notes)
        payload["kpi_definition_hash"] = self.hash
        payload["is_degenerate"] = self.is_degenerate()
        return payload


@dataclass(frozen=True)
class KpiMeasurement:
    """One measured KPI value with everything needed to judge it."""

    kpi_definition_hash: str
    game: str
    arm_id: str
    n_tickets: int
    tolerance: int
    coverage: float
    coverage_ci: tuple[float, float]
    n_targets: int
    coverage_source: str
    lower_bound_tickets: int
    efficiency: float
    arm_delta: float | None = None
    e_value: float | None = None
    adjusted_p_value: float | None = None
    protocol_hash: str | None = None
    schema_version: str = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.efficiency > 1.0 + 1e-9:
            raise ValueError(
                f"efficiency {self.efficiency:.6f} exceeds the packing bound; this is "
                "impossible for a valid pool and indicates a defect or a leak"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coverage_ci"] = list(self.coverage_ci)
        return payload


# --------------------------------------------------------------------------------------
# cost
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CostEstimate:
    """Ticket spend, and the exact-match expectation -- deliberately never coverage-based."""

    game: str
    n_tickets: int
    unit_price_jpy: int
    total_cost_jpy: int
    exact_match_probability: float
    price_provenance: str
    payout_provenance: str
    expected_return_jpy: float | None = None
    net_expected_jpy: float | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class CostModel:
    """Ticket cost and exact-match probability.

    Expected return is left as ``None`` unless a payout table is supplied, and it is
    *never* computed from a coverage figure. Coverage at tolerance >= 1 does not win
    anything, so multiplying coverage by a jackpot would produce a number that looks like
    a return and is not one.
    """

    unit_price_jpy: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_UNIT_PRICE_JPY))
    payout_table_jpy: dict[str, dict[str, float]] = field(default_factory=dict)
    price_provenance: str = (
        "UNVERIFIED: loto.combinatorics.bounds.DEFAULT_UNIT_PRICE_JPY. Confirm against "
        "the operator's published price list before quoting."
    )
    payout_provenance: str = (
        "NOT SUPPLIED: no payout table configured, so expected return is not computed."
    )

    def estimate(self, *, game: str, n_tickets: int) -> CostEstimate:
        geometry = geometry_for(game)
        price = self.unit_price_jpy.get(game)
        if price is None:
            raise ValueError(f"no unit price configured for game={game!r}")
        exact = min(1.0, n_tickets / geometry.outcome_space)
        warnings: list[str] = [
            "total_cost_jpy is the purchase cost of the pool. Coverage at tolerance >= 1 "
            "is not a prize condition in any of these games, so cost must not be compared "
            "against a coverage figure as though coverage were a return.",
        ]
        expected_return: float | None = None
        net: float | None = None
        table = self.payout_table_jpy.get(game)
        if table:
            top = float(table.get("top", 0.0))
            expected_return = exact * top
            net = expected_return - n_tickets * price
            warnings.append(
                "expected_return_jpy uses only the top prize tier and ignores lower tiers "
                "and pari-mutuel splitting; it is a lower bound on gross return and an "
                "optimistic bound on net loss magnitude."
            )
        else:
            warnings.append(
                "expected_return_jpy is None because no payout table was configured. "
                "Do not infer a return from coverage."
            )
        return CostEstimate(
            game=geometry.key,
            n_tickets=n_tickets,
            unit_price_jpy=price,
            total_cost_jpy=n_tickets * price,
            exact_match_probability=exact,
            price_provenance=self.price_provenance,
            payout_provenance=(
                self.payout_provenance if not table else "SUPPLIED: payout_table_jpy"
            ),
            expected_return_jpy=expected_return,
            net_expected_jpy=net,
            warnings=tuple(warnings),
        )

    def break_even_tickets(self, *, game: str) -> float | None:
        """Ticket count at which top-tier expectation equals spend, if a payout is known."""
        table = self.payout_table_jpy.get(game)
        price = self.unit_price_jpy.get(game)
        if not table or price is None:
            return None
        geometry = geometry_for(game)
        top = float(table.get("top", 0.0))
        if top <= 0:
            return None
        # n/|Omega| * top = n * price  =>  independent of n unless top/|Omega| == price
        ratio = top / geometry.outcome_space
        return math.inf if ratio > price else None
