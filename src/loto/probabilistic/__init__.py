"""Probabilistic-programming extension for the Loto forecasting platform.

The package is dependency-light at import time. All catalog models have one declared
and implemented primary path. The original 72 PPL-01 model IDs remain unchanged,
while PPL-02 models are added without substitution: exact analytic, PyMC, NumPyro,
Pyro, PyMC-BART or ArviZ. Backend availability is probed explicitly, and native mode
never silently substitutes the legacy reference engine.
"""

from loto.probabilistic.catalog import (
    catalog_counts,
    get_inference_profile,
    get_probabilistic_model_spec,
    list_inference_profiles,
    list_probabilistic_model_specs,
)
from loto.probabilistic.contracts import (
    CompatibilityDecision,
    DiagnosticReport,
    InferenceProfileSpec,
    PredictiveDistribution,
    ProbabilisticModelSpec,
    ProbabilisticRunConfig,
)
from loto.probabilistic.experiment_tracking import (
    ExperimentPersistenceError,
    ExperimentTrackingConfig,
    ExperimentTrackingReport,
    evaluate_and_persist_conditional_bernoulli,
    persist_experiment_tracking,
)
from loto.probabilistic.priors import (
    PriorProfileDecision,
    PriorProfileSpec,
    PriorToyVerificationReport,
    decide_prior_profile_compatibility,
    get_prior_profile,
    list_prior_profiles,
    verify_prior_profile_toy,
)
from loto.probabilistic.subset_evaluation import (
    SubsetEvaluationResult,
    evaluate_conditional_bernoulli,
    verify_fixed_prediction,
)

__all__ = [
    "ExperimentTrackingReport",
    "ExperimentTrackingConfig",
    "ExperimentPersistenceError",
    "CompatibilityDecision",
    "DiagnosticReport",
    "InferenceProfileSpec",
    "PredictiveDistribution",
    "PriorProfileDecision",
    "PriorProfileSpec",
    "PriorToyVerificationReport",
    "ProbabilisticModelSpec",
    "ProbabilisticRunConfig",
    "SubsetEvaluationResult",
    "catalog_counts",
    "persist_experiment_tracking",
    "evaluate_and_persist_conditional_bernoulli",
    "evaluate_conditional_bernoulli",
    "get_inference_profile",
    "get_probabilistic_model_spec",
    "list_inference_profiles",
    "list_probabilistic_model_specs",
    "decide_prior_profile_compatibility",
    "get_prior_profile",
    "list_prior_profiles",
    "verify_prior_profile_toy",
    "verify_fixed_prediction",
]
