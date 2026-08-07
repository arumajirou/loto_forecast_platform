"""Feature Availability Registry foundation."""

from .contracts import (
    DataSplit,
    FeatureAvailability,
    FeatureDefinition,
    FeatureManifest,
    FeatureMaterialization,
    FeatureSource,
    MissingPolicy,
    PreprocessorFitEvidence,
    PreprocessorKind,
    SplitManifest,
    SplitWindow,
    TemporalClass,
)
from .manifest import (
    ManifestIntegrityError,
    canonical_manifest_bytes,
    manifest_sha256,
    read_feature_manifest,
    write_feature_manifest,
)
from .validator import (
    FeatureAvailabilityError,
    FeatureValidationReport,
    ValidationIssue,
    ValidationIssueCode,
    assert_feature_manifest_valid,
    validate_feature_manifest,
)

__all__ = [
    "DataSplit",
    "FeatureAvailability",
    "FeatureAvailabilityError",
    "FeatureDefinition",
    "FeatureManifest",
    "FeatureMaterialization",
    "FeatureSource",
    "FeatureValidationReport",
    "ManifestIntegrityError",
    "MissingPolicy",
    "PreprocessorFitEvidence",
    "PreprocessorKind",
    "SplitManifest",
    "SplitWindow",
    "TemporalClass",
    "ValidationIssue",
    "ValidationIssueCode",
    "assert_feature_manifest_valid",
    "canonical_manifest_bytes",
    "manifest_sha256",
    "read_feature_manifest",
    "validate_feature_manifest",
    "write_feature_manifest",
]
