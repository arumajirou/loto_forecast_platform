"""Typed causal-identification contracts with fail-closed eligibility."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CausalDesign = Literal[
    "association_only",
    "pre_post_event",
    "interrupted_time_series",
    "controlled_event_study",
]


class CausalDag(BaseModel):
    """A small declared directed acyclic graph used for identification bookkeeping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[str, ...] = Field(min_length=2)
    edges: tuple[tuple[str, str], ...] = ()

    @model_validator(mode="after")
    def validate_graph(self) -> CausalDag:
        if any(not node.strip() for node in self.nodes):
            raise ValueError("DAG nodes must be non-empty strings")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("DAG nodes must be unique")
        node_set = set(self.nodes)
        adjacency: dict[str, list[str]] = {node: [] for node in self.nodes}
        for source, target in self.edges:
            if source not in node_set or target not in node_set:
                raise ValueError(f"DAG edge references unknown node: {(source, target)}")
            if source == target:
                raise ValueError("DAG self-edges are forbidden")
            adjacency[source].append(target)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("DAG contains a directed cycle")
            if node in visited:
                return
            visiting.add(node)
            for target in adjacency[node]:
                visit(target)
            visiting.remove(node)
            visited.add(node)

        for node in self.nodes:
            visit(node)
        return self

    def has_directed_path(self, source: str, target: str) -> bool:
        if source not in self.nodes or target not in self.nodes:
            return False
        adjacency: dict[str, list[str]] = {node: [] for node in self.nodes}
        for left, right in self.edges:
            adjacency[left].append(right)
        stack = [source]
        visited: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adjacency[current])
        return False


class IdentificationPlan(BaseModel):
    """Pre-declared identification assumptions for one causal hypothesis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis_id: str = Field(min_length=1)
    dag: CausalDag
    exposure: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    adjustment_set: tuple[str, ...] = ()
    design: CausalDesign = "association_only"
    intervention_time_known: bool = False
    temporal_order_verified: bool = False
    confounders_declared: bool = False
    negative_control_pre_registered: bool = False
    no_concurrent_interventions_asserted: bool = False
    control_series_declared: bool = False

    @model_validator(mode="after")
    def validate_identification_nodes(self) -> IdentificationPlan:
        node_set = set(self.dag.nodes)
        if self.exposure not in node_set:
            raise ValueError("exposure must be a DAG node")
        if self.outcome not in node_set:
            raise ValueError("outcome must be a DAG node")
        if self.exposure == self.outcome:
            raise ValueError("exposure and outcome must differ")
        if len(set(self.adjustment_set)) != len(self.adjustment_set):
            raise ValueError("adjustment_set must contain unique nodes")
        forbidden = {self.exposure, self.outcome}
        for node in self.adjustment_set:
            if node not in node_set:
                raise ValueError(f"adjustment node is not in DAG: {node}")
            if node in forbidden:
                raise ValueError("adjustment_set cannot contain exposure or outcome")
        return self


class IdentificationAssessment(BaseModel):
    """Explicit eligibility decision; eligibility is not proof of causality."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis_id: str
    design: CausalDesign
    causal_claim_eligible: bool
    unmet_requirements: tuple[str, ...]
    interpretation: str


def assess_identification(plan: IdentificationPlan) -> IdentificationAssessment:
    """Fail closed unless the declared design satisfies the minimum v1 identification gate."""
    unmet: list[str] = []
    if plan.design not in {"interrupted_time_series", "controlled_event_study"}:
        unmet.append("identified quasi-experimental design is required")
    if not plan.intervention_time_known:
        unmet.append("intervention time must be known before outcome analysis")
    if not plan.temporal_order_verified:
        unmet.append("exposure-before-outcome temporal order must be verified")
    if not plan.confounders_declared:
        unmet.append("candidate confounders and adjustment strategy must be declared")
    if not plan.negative_control_pre_registered:
        unmet.append("a negative-control/placebo test must be pre-registered")
    if not plan.no_concurrent_interventions_asserted:
        unmet.append("concurrent interventions must be ruled out or declared")
    if plan.design == "controlled_event_study" and not plan.control_series_declared:
        unmet.append("controlled event study requires a declared control series")
    if not plan.dag.has_directed_path(plan.exposure, plan.outcome):
        unmet.append("DAG must declare a directed exposure-to-outcome path")

    eligible = not unmet
    interpretation = (
        "eligible for guarded causal interpretation subject to model assumptions and falsification"
        if eligible
        else "association/descriptive evidence only; causal claim must remain closed"
    )
    return IdentificationAssessment(
        hypothesis_id=plan.hypothesis_id,
        design=plan.design,
        causal_claim_eligible=eligible,
        unmet_requirements=tuple(unmet),
        interpretation=interpretation,
    )
