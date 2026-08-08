"""Shared, auditable search-policy resolution for NeuralForecast AutoModels."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

AUTO_TPE_MIN_SAMPLES = 10


class SearchPolicyError(ValueError):
    """Base class for invalid or unsupported search-policy requests."""


class SearchPolicyDependencyError(RuntimeError):
    """Raised when an effective search algorithm cannot be imported."""


class SearchBackend(StrEnum):
    OPTUNA = "optuna"
    RAY = "ray"


class SearchStrategy(StrEnum):
    AUTO = "auto"
    RANDOM = "random"
    TPE = "tpe"
    CMAES = "cmaes"


class SearchPolicyDecision(BaseModel):
    """Serializable evidence for one deterministic search-policy decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    model_name: str | None = None
    backend: SearchBackend
    requested_strategy: SearchStrategy
    resolved_strategy: SearchStrategy
    algorithm_name: str
    algorithm_module: str
    algorithm_kwargs: dict[str, Any] = Field(default_factory=dict)
    effective_algorithm_name: str
    search_seed: int
    num_samples: int
    reason_codes: tuple[str, ...]
    fallback_used: bool = False
    fallback_reason: str | None = None

    @field_validator("num_samples")
    @classmethod
    def positive_samples(cls, value: int) -> int:
        if value < 1:
            raise ValueError("num_samples must be >= 1")
        return value


@dataclass(frozen=True)
class SearchAlgorithmMaterialization:
    """Runtime search object plus the effective decision persisted as evidence."""

    algorithm: Any | None
    decision: SearchPolicyDecision


def resolve_search_policy(
    *,
    backend: SearchBackend | str,
    strategy: SearchStrategy | str,
    search_seed: int,
    num_samples: int,
    model_name: str | None = None,
) -> SearchPolicyDecision:
    """Resolve a search policy without importing Optuna, Ray, or NeuralForecast."""

    try:
        resolved_backend = SearchBackend(backend)
    except ValueError as exc:
        raise SearchPolicyError(f"unsupported search backend: {backend}") from exc
    try:
        requested = SearchStrategy(strategy)
    except ValueError as exc:
        raise SearchPolicyError(f"unsupported search strategy: {strategy}") from exc
    if num_samples < 1:
        raise SearchPolicyError("num_samples must be >= 1")
    if model_name == "AutoHINT" and resolved_backend is SearchBackend.OPTUNA:
        raise SearchPolicyError(
            "AutoHINT supports only backend='ray' in the pinned NeuralForecast runtime"
        )

    reasons = ["EXPLICIT_STRATEGY"]
    resolved = requested
    if requested is SearchStrategy.AUTO:
        reasons = ["AUTO_STRATEGY"]
        resolved = (
            SearchStrategy.RANDOM if num_samples < AUTO_TPE_MIN_SAMPLES else SearchStrategy.TPE
        )
        reasons.append(
            "BUDGET_LT_AUTO_TPE_THRESHOLD"
            if resolved is SearchStrategy.RANDOM
            else "BUDGET_GE_AUTO_TPE_THRESHOLD"
        )

    if resolved_backend is SearchBackend.RAY:
        if resolved is SearchStrategy.CMAES:
            raise SearchPolicyError("strategy='cmaes' is unsupported for backend='ray'")
        if resolved is SearchStrategy.RANDOM:
            algorithm_name = "BasicVariantGenerator"
            algorithm_module = "ray.tune.search.basic_variant"
            algorithm_kwargs = {"random_state": search_seed}
        else:
            algorithm_name = "OptunaSearch"
            algorithm_module = "ray.tune.search.optuna"
            algorithm_kwargs = {"seed": search_seed}
    elif resolved is SearchStrategy.RANDOM:
        algorithm_name = "RandomSampler"
        algorithm_module = "optuna.samplers"
        algorithm_kwargs = {"seed": search_seed}
    elif resolved is SearchStrategy.CMAES:
        algorithm_name = "CmaEsSampler"
        algorithm_module = "optuna.samplers"
        algorithm_kwargs = {"seed": search_seed}
    else:
        algorithm_name = "TPESampler"
        algorithm_module = "optuna.samplers"
        algorithm_kwargs = {
            "seed": search_seed,
            "multivariate": True,
            "group": True,
        }

    return SearchPolicyDecision(
        model_name=model_name,
        backend=resolved_backend,
        requested_strategy=requested,
        resolved_strategy=resolved,
        algorithm_name=algorithm_name,
        algorithm_module=algorithm_module,
        algorithm_kwargs=algorithm_kwargs,
        effective_algorithm_name=algorithm_name,
        search_seed=search_seed,
        num_samples=num_samples,
        reason_codes=tuple(reasons),
    )


def instantiate_search_algorithm(
    decision: SearchPolicyDecision,
    *,
    allow_fallback: bool = False,
) -> SearchAlgorithmMaterialization:
    """Instantiate the resolved algorithm and fail closed unless fallback is explicit."""

    try:
        if decision.algorithm_module == "optuna.samplers":
            import optuna

            cls = getattr(optuna.samplers, decision.algorithm_name)
        elif decision.algorithm_name == "BasicVariantGenerator":
            from ray.tune.search.basic_variant import BasicVariantGenerator

            cls = BasicVariantGenerator
        elif decision.algorithm_name == "OptunaSearch":
            from ray.tune.search.optuna import OptunaSearch

            cls = OptunaSearch
        else:
            raise SearchPolicyError(
                f"unsupported algorithm contract: {decision.algorithm_module}."
                f"{decision.algorithm_name}"
            )
        algorithm = cls(**decision.algorithm_kwargs)
    except ImportError as exc:
        if not allow_fallback:
            raise SearchPolicyDependencyError(
                f"cannot import {decision.algorithm_module} for {decision.effective_algorithm_name}"
            ) from exc
        fallback = decision.model_copy(
            update={
                "effective_algorithm_name": "library_default",
                "fallback_used": True,
                "fallback_reason": f"dependency unavailable: {decision.algorithm_module}",
            }
        )
        return SearchAlgorithmMaterialization(algorithm=None, decision=fallback)

    return SearchAlgorithmMaterialization(algorithm=algorithm, decision=decision)
