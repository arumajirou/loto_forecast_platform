"""Fail-closed local AutoTimeLLM extension for NeuralForecast 3.2.0."""

from .contracts import (
    ArchitectureProfile,
    ArchitectureSpec,
    PinnedLLMIdentity,
    SnapshotFileEvidence,
    SnapshotModelMetadata,
    SnapshotVerification,
    TrialParameters,
    load_snapshot_model_metadata,
    resolve_architecture,
    verify_snapshot,
)
from .runtime import (
    RuntimeDependencyError,
    construct_auto_timellm,
    get_auto_timellm_class,
    get_pinned_timellm_class,
    runtime_dependency_status,
)

__all__ = [
    "ArchitectureProfile",
    "ArchitectureSpec",
    "PinnedLLMIdentity",
    "RuntimeDependencyError",
    "SnapshotFileEvidence",
    "SnapshotModelMetadata",
    "SnapshotVerification",
    "TrialParameters",
    "construct_auto_timellm",
    "get_auto_timellm_class",
    "get_pinned_timellm_class",
    "load_snapshot_model_metadata",
    "resolve_architecture",
    "runtime_dependency_status",
    "verify_snapshot",
]
