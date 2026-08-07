"""Clock Health Gate v1 public surface."""

from .canonical import (
    CanonicalizationError,
    canonical_json,
    loads_strict_json,
    loads_strict_object,
    sha256_bytes,
    sha256_canonical,
)
from .chronyc import (
    ChronycAdapter,
    ChronycProbeArtifacts,
    CommandResult,
    SubprocessCommandRunner,
    parse_chronyc_observation,
    verify_raw_observation,
)
from .contracts import (
    CheckOutcome,
    ClockCheckResult,
    ClockCommandEvidence,
    ClockContinuityEvidence,
    ClockHealthDecision,
    ClockHealthPolicy,
    ClockHealthStatus,
    ClockObservation,
    ClockParserEvidence,
    ClockSourceObservation,
    LeapStatus,
    SourceSelectionState,
)
from .evaluator import evaluate_clock_health
from .io import (
    load_model_json,
    verify_evidence_bundle,
    write_evidence_bundle,
    write_json_atomic,
)

__all__ = [
    "CanonicalizationError",
    "CheckOutcome",
    "ChronycAdapter",
    "ChronycProbeArtifacts",
    "ClockCheckResult",
    "ClockCommandEvidence",
    "ClockContinuityEvidence",
    "ClockHealthDecision",
    "ClockHealthPolicy",
    "ClockHealthStatus",
    "ClockObservation",
    "ClockParserEvidence",
    "ClockSourceObservation",
    "CommandResult",
    "LeapStatus",
    "SourceSelectionState",
    "SubprocessCommandRunner",
    "canonical_json",
    "evaluate_clock_health",
    "load_model_json",
    "loads_strict_json",
    "loads_strict_object",
    "parse_chronyc_observation",
    "sha256_bytes",
    "sha256_canonical",
    "verify_evidence_bundle",
    "verify_raw_observation",
    "write_evidence_bundle",
    "write_json_atomic",
]
