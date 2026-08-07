"""Third-party-verifiable evidence schemas for prediction and actual locks."""

from .canonical import (
    canonical_headers,
    canonical_json_bytes,
    canonical_sha256,
    headers_sha256,
    material_inventory_sha256,
    sha256_bytes,
    sha256_file,
)
from .contracts import (
    ActualSourceEvidence,
    CorrectionEvidence,
    EvidenceDecision,
    ExternalVerificationResult,
    OfflineVerificationReport,
    ParserEvidence,
    SignatureEvidence,
    SourceRevisionEvidence,
    ThirdPartyEvidenceBundle,
    TrustedTimeEvidence,
    VerificationMaterial,
)
from .corrections import verify_correction_chain
from .interfaces import VerifierRegistry
from .legacy import legacy_actual_source_evidence, legacy_bundle, legacy_prediction_time_evidence
from .offline_verifier import report_as_dict, verify_evidence_bundle
from .statuses import (
    EvidenceStatus,
    OfflineVerificationStatus,
    PublicVerifiability,
    RevisionKind,
    SignatureKind,
    TimestampAuthority,
    VerificationDomain,
)

__all__ = [
    "ActualSourceEvidence",
    "CorrectionEvidence",
    "EvidenceDecision",
    "EvidenceStatus",
    "ExternalVerificationResult",
    "OfflineVerificationReport",
    "OfflineVerificationStatus",
    "ParserEvidence",
    "PublicVerifiability",
    "RevisionKind",
    "SignatureEvidence",
    "SignatureKind",
    "SourceRevisionEvidence",
    "ThirdPartyEvidenceBundle",
    "TimestampAuthority",
    "TrustedTimeEvidence",
    "VerificationDomain",
    "VerificationMaterial",
    "VerifierRegistry",
    "canonical_headers",
    "canonical_json_bytes",
    "canonical_sha256",
    "headers_sha256",
    "legacy_actual_source_evidence",
    "legacy_bundle",
    "legacy_prediction_time_evidence",
    "material_inventory_sha256",
    "report_as_dict",
    "sha256_bytes",
    "sha256_file",
    "verify_correction_chain",
    "verify_evidence_bundle",
]
