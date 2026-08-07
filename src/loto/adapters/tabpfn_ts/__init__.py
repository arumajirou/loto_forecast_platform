"""Versioned TabPFN-TS contracts and safety gates.

This package is intentionally isolated from the shared provider catalog until the
contract, checkpoint provenance, and runtime evidence are independently certified.
"""

from .contract import (
    ArtifactReference,
    CandidateProbability,
    CandidateScore,
    Device,
    EffectiveArguments,
    FeatureManifest,
    ForecastValue,
    GPUEvidence,
    HistorySeries,
    KnownFutureCovariateRow,
    LicenseEvidence,
    ModelIdentity,
    OutputSelection,
    QuantileForecast,
    ResponseStatus,
    RuntimeEvidence,
    TabPFNTSRequestV2,
    TabPFNTSResponseV2,
    TaskFormulation,
    TimeSemantics,
)
from .geometry import GAME_GEOMETRIES, GameGeometry, geometry_for
from .hash_gate import (
    CheckpointEvidence,
    CheckpointGateSpec,
    CheckpointIntegrityError,
    formal_runtime_environment,
    guarded_checkpoint_load,
    sha256_file,
    verify_checkpoint_before_load,
)
from .legacy_v1_adapter import legacy_v1_request_to_v2, v2_response_to_legacy_v1
from .manifests import (
    LANE_MANIFESTS,
    PACKAGE_MANIFEST,
    CheckpointLane,
    ExecutionStatus,
    lane_manifest,
    require_executable_lane,
)
from .validation import (
    rank_candidate_scores,
    require_strict_gpu_success,
    validate_calibrated_probabilities,
    validate_local_batch_parity,
)

__all__ = [
    "ArtifactReference",
    "CandidateProbability",
    "CandidateScore",
    "CheckpointEvidence",
    "CheckpointGateSpec",
    "CheckpointIntegrityError",
    "CheckpointLane",
    "Device",
    "EffectiveArguments",
    "ExecutionStatus",
    "FeatureManifest",
    "ForecastValue",
    "GAME_GEOMETRIES",
    "GPUEvidence",
    "GameGeometry",
    "HistorySeries",
    "KnownFutureCovariateRow",
    "LANE_MANIFESTS",
    "LicenseEvidence",
    "ModelIdentity",
    "OutputSelection",
    "PACKAGE_MANIFEST",
    "QuantileForecast",
    "ResponseStatus",
    "RuntimeEvidence",
    "TabPFNTSRequestV2",
    "TabPFNTSResponseV2",
    "TaskFormulation",
    "TimeSemantics",
    "formal_runtime_environment",
    "geometry_for",
    "guarded_checkpoint_load",
    "lane_manifest",
    "legacy_v1_request_to_v2",
    "rank_candidate_scores",
    "require_executable_lane",
    "require_strict_gpu_success",
    "sha256_file",
    "v2_response_to_legacy_v1",
    "validate_calibrated_probabilities",
    "validate_local_batch_parity",
    "verify_checkpoint_before_load",
]
