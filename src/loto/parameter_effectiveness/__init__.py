"""Cross-platform model parameter effectiveness validation."""

from .contracts import (
    EffectOutcome,
    EffectSurface,
    ExpectedRelation,
    ParameterProbeResult,
    ParameterProbeSpec,
    ParameterScope,
    ParameterSuiteSpec,
    ProbeRunObservation,
)
from .core import AdapterRegistry, FunctionProbeAdapter, evaluate_probe, run_suite

__all__ = [
    "AdapterRegistry",
    "EffectOutcome",
    "EffectSurface",
    "ExpectedRelation",
    "FunctionProbeAdapter",
    "ParameterProbeResult",
    "ParameterProbeSpec",
    "ParameterScope",
    "ParameterSuiteSpec",
    "ProbeRunObservation",
    "evaluate_probe",
    "run_suite",
]
