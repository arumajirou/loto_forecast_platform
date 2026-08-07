from __future__ import annotations

import math
from dataclasses import dataclass

from .contracts import Capability, HarnessStatus, ModelDescriptor, RiskLevel
from .errors import ConfigurationError
from .registry import ModelRegistry


@dataclass(frozen=True)
class RouteRequest:
    required_capabilities: frozenset[Capability] = frozenset({Capability.CHAT})
    role: str | None = None
    minimum_context: int = 0
    risk: RiskLevel = RiskLevel.MEDIUM


@dataclass(frozen=True)
class RouteDecision:
    model: ModelDescriptor
    score: float
    reasons: tuple[str, ...]


def _normalized_tps(value: float) -> float:
    return min(1.0, math.log1p(value) / math.log1p(100.0))


def score_model(model: ModelDescriptor, request: RouteRequest) -> RouteDecision | None:
    if not model.enabled or model.status in {HarnessStatus.BLOCKED, HarnessStatus.FAILED}:
        return None
    if not request.required_capabilities.issubset(model.capabilities):
        return None
    effective_context = model.certified_context
    if (
        effective_context < request.minimum_context
        and model.virtual_context < request.minimum_context
    ):
        return None
    if request.role and model.roles and request.role not in model.roles:
        return None

    p = model.performance
    score = (
        0.25 * p.task_quality
        + 0.20 * p.tool_success
        + 0.15 * p.schema_success
        + 0.15 * p.test_pass_after_patch
        + 0.10 * p.reviewer_acceptance
        + 0.05 * _normalized_tps(p.generation_tps)
        + 0.10 * p.stability
        - 0.25 * p.timeout_rate
        - 0.35 * p.oom_rate
    )
    reasons = [f"effective_context={effective_context}"]
    if model.status == HarnessStatus.VERIFIED:
        score += 0.05
        reasons.append("verified_bonus")
    if request.role and request.role in model.roles:
        score += 0.05
        reasons.append(f"role={request.role}")
    if request.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        score += 0.05 * p.reviewer_acceptance
        reasons.append("risk_adjustment")
    return RouteDecision(model=model, score=score, reasons=tuple(reasons))


class ModelRouter:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def route(self, request: RouteRequest) -> RouteDecision:
        candidates = [
            decision
            for model in self.registry.enabled()
            if (decision := score_model(model, request)) is not None
        ]
        if not candidates:
            raise ConfigurationError("no model satisfies routing requirements")
        return max(candidates, key=lambda decision: (decision.score, decision.model.key))
