"""Probabilistic-programming extension for the Loto forecasting platform.

The package is dependency-light at import time. All 72 catalog models have one declared
and implemented primary path: exact analytic, PyMC, NumPyro, Pyro, PyMC-BART or ArviZ.
Backend availability is probed explicitly and native mode never silently substitutes the
legacy reference engine.
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

__all__ = [
    "CompatibilityDecision",
    "DiagnosticReport",
    "InferenceProfileSpec",
    "PredictiveDistribution",
    "ProbabilisticModelSpec",
    "ProbabilisticRunConfig",
    "catalog_counts",
    "get_inference_profile",
    "get_probabilistic_model_spec",
    "list_inference_profiles",
    "list_probabilistic_model_specs",
]
