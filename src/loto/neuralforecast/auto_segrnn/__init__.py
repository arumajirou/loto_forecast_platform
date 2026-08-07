"""Inactive local NeuralForecast AutoSegRNN extension."""

from .contracts import (
    MODEL_ID,
    SCHEMA_VERSION,
    UPSTREAM_LICENSE,
    UPSTREAM_REPOSITORY,
    UPSTREAM_REVISION,
    UPSTREAM_SOURCE_PATH,
    ArchitectureProfile,
    ArchitectureSpec,
    TrainingProfile,
    TrainingSpec,
    TrialParameters,
    resolve_architecture,
    resolve_training,
)
from .runtime import (
    RuntimeDependencyError,
    construct_auto_segrnn,
    get_auto_segrnn_class,
    get_segrnn_class,
    runtime_dependency_status,
)

__all__ = [
    "ArchitectureProfile",
    "ArchitectureSpec",
    "MODEL_ID",
    "RuntimeDependencyError",
    "SCHEMA_VERSION",
    "TrainingProfile",
    "TrainingSpec",
    "TrialParameters",
    "UPSTREAM_LICENSE",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_REVISION",
    "UPSTREAM_SOURCE_PATH",
    "construct_auto_segrnn",
    "get_auto_segrnn_class",
    "get_segrnn_class",
    "resolve_architecture",
    "resolve_training",
    "runtime_dependency_status",
]
