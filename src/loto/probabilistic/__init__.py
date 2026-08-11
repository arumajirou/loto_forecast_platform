"""Probabilistic-programming extension for the Loto forecasting platform.

The package is dependency-light at import time. Public symbols are resolved lazily so
consumers of lightweight submodules such as ``loto.probabilistic.decoder`` do not need the
full probabilistic catalog/tracking dependency set merely to import the package.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "catalog_counts": ("loto.probabilistic.catalog", "catalog_counts"),
    "get_inference_profile": ("loto.probabilistic.catalog", "get_inference_profile"),
    "get_probabilistic_model_spec": (
        "loto.probabilistic.catalog",
        "get_probabilistic_model_spec",
    ),
    "list_inference_profiles": ("loto.probabilistic.catalog", "list_inference_profiles"),
    "list_probabilistic_model_specs": (
        "loto.probabilistic.catalog",
        "list_probabilistic_model_specs",
    ),
    "CompatibilityDecision": ("loto.probabilistic.contracts", "CompatibilityDecision"),
    "DiagnosticReport": ("loto.probabilistic.contracts", "DiagnosticReport"),
    "InferenceProfileSpec": ("loto.probabilistic.contracts", "InferenceProfileSpec"),
    "PredictiveDistribution": ("loto.probabilistic.contracts", "PredictiveDistribution"),
    "ProbabilisticModelSpec": ("loto.probabilistic.contracts", "ProbabilisticModelSpec"),
    "ProbabilisticRunConfig": ("loto.probabilistic.contracts", "ProbabilisticRunConfig"),
    "ExperimentPersistenceError": (
        "loto.probabilistic.experiment_tracking",
        "ExperimentPersistenceError",
    ),
    "ExperimentTrackingConfig": (
        "loto.probabilistic.experiment_tracking",
        "ExperimentTrackingConfig",
    ),
    "ExperimentTrackingReport": (
        "loto.probabilistic.experiment_tracking",
        "ExperimentTrackingReport",
    ),
    "evaluate_and_persist_conditional_bernoulli": (
        "loto.probabilistic.experiment_tracking",
        "evaluate_and_persist_conditional_bernoulli",
    ),
    "persist_experiment_tracking": (
        "loto.probabilistic.experiment_tracking",
        "persist_experiment_tracking",
    ),
    "PriorProfileDecision": ("loto.probabilistic.priors", "PriorProfileDecision"),
    "PriorProfileSpec": ("loto.probabilistic.priors", "PriorProfileSpec"),
    "PriorToyVerificationReport": (
        "loto.probabilistic.priors",
        "PriorToyVerificationReport",
    ),
    "decide_prior_profile_compatibility": (
        "loto.probabilistic.priors",
        "decide_prior_profile_compatibility",
    ),
    "get_prior_profile": ("loto.probabilistic.priors", "get_prior_profile"),
    "list_prior_profiles": ("loto.probabilistic.priors", "list_prior_profiles"),
    "verify_prior_profile_toy": ("loto.probabilistic.priors", "verify_prior_profile_toy"),
    "SubsetEvaluationResult": (
        "loto.probabilistic.subset_evaluation",
        "SubsetEvaluationResult",
    ),
    "evaluate_conditional_bernoulli": (
        "loto.probabilistic.subset_evaluation",
        "evaluate_conditional_bernoulli",
    ),
    "verify_fixed_prediction": (
        "loto.probabilistic.subset_evaluation",
        "verify_fixed_prediction",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
