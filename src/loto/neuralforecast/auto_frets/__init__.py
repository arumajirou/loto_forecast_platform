"""Inactive local NeuralForecast FreTS and AutoFreTS extension."""

from .contracts import (
    ArchitectureProfile,
    ArchitectureSpec,
    MODEL_ID,
    SCHEMA_VERSION,
    TrainingProfile,
    TrainingSpec,
    TrialParameters,
    expected_parameter_count,
    resolve_architecture,
    resolve_training,
)
from .runtime import (
    RuntimeDependencyError,
    construct_auto_frets,
    get_auto_frets_class,
    get_frets_class,
    runtime_dependency_status,
)


def __getattr__(name: str):
    if name == "FreTS":
        return get_frets_class()
    if name == "AutoFreTS":
        return get_auto_frets_class()
    raise AttributeError(name)


__all__ = [
    "ArchitectureProfile",
    "ArchitectureSpec",
    "AutoFreTS",
    "FreTS",
    "MODEL_ID",
    "RuntimeDependencyError",
    "SCHEMA_VERSION",
    "TrainingProfile",
    "TrainingSpec",
    "TrialParameters",
    "construct_auto_frets",
    "expected_parameter_count",
    "get_auto_frets_class",
    "get_frets_class",
    "resolve_architecture",
    "resolve_training",
    "runtime_dependency_status",
]
