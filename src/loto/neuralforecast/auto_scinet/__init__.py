"""Local NeuralForecast SCINet and AutoSCINet extension."""

from typing import Any

from .contracts import (
    MODEL_ID,
    SCHEMA_VERSION,
    TARGET_NEURALFORECAST_VERSION,
    UPSTREAM_LICENSE,
    UPSTREAM_REPOSITORY,
    UPSTREAM_REVISION,
    UPSTREAM_SOURCE_GIT_BLOB,
    UPSTREAM_SOURCE_PATH,
    ArchitectureProfile,
    ArchitectureSpec,
    TrainingProfile,
    TrainingSpec,
    TrialParameters,
    expected_parameter_count,
    resolve_architecture,
    resolve_training,
)
from .runtime import (
    RuntimeDependencyError,
    construct_auto_scinet,
    get_auto_scinet_class,
    get_scinet_class,
    runtime_dependency_status,
)


def __getattr__(name: str) -> Any:
    if name == "SCINet":
        return get_scinet_class()
    if name == "AutoSCINet":
        return get_auto_scinet_class()
    raise AttributeError(name)


__all__ = [
    "ArchitectureProfile",
    "ArchitectureSpec",
    "AutoSCINet",
    "MODEL_ID",
    "RuntimeDependencyError",
    "SCHEMA_VERSION",
    "SCINet",
    "TARGET_NEURALFORECAST_VERSION",
    "TrainingProfile",
    "TrainingSpec",
    "TrialParameters",
    "UPSTREAM_LICENSE",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_REVISION",
    "UPSTREAM_SOURCE_GIT_BLOB",
    "UPSTREAM_SOURCE_PATH",
    "construct_auto_scinet",
    "expected_parameter_count",
    "get_auto_scinet_class",
    "get_scinet_class",
    "resolve_architecture",
    "resolve_training",
    "runtime_dependency_status",
]
