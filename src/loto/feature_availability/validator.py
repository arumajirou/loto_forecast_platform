"""Fail-closed validation for feature availability manifests."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .contracts import (
    UNKNOWN_REVISIONS,
    DataSplit,
    FeatureManifest,
    StrictModel,
    TemporalClass,
)


class ValidationIssueCode(StrEnum):
    AVAILABLE_AFTER_PREDICTION_CUTOFF = "AVAILABLE_AFTER_PREDICTION_CUTOFF"
    MATERIALIZED_AFTER_PREDICTION_CUTOFF = "MATERIALIZED_AFTER_PREDICTION_CUTOFF"
    UNKNOWN_REVISION = "UNKNOWN_REVISION"
    FUTURE_TARGET_DEPENDENCY = "FUTURE_TARGET_DEPENDENCY"
    PREPROCESSOR_FIT_OUTSIDE_TRAIN = "PREPROCESSOR_FIT_OUTSIDE_TRAIN"
    POST_TRAIN_ACTUAL_DEPENDENCY = "POST_TRAIN_ACTUAL_DEPENDENCY"
    DUPLICATE_FEATURE_IDENTITY = "DUPLICATE_FEATURE_IDENTITY"
    DUPLICATE_FEATURE_NAME = "DUPLICATE_FEATURE_NAME"
    SOURCE_HASH_CHANGED = "SOURCE_HASH_CHANGED"
    UNKNOWN_TEMPORAL_CLASS = "UNKNOWN_TEMPORAL_CLASS"
    NOT_KNOWN_AT_PREDICTION_TIME = "NOT_KNOWN_AT_PREDICTION_TIME"
    SOURCE_REFERENCE_MISMATCH = "SOURCE_REFERENCE_MISMATCH"
    DEFINITION_MISMATCH = "DEFINITION_MISMATCH"
    AVAILABILITY_MISMATCH = "AVAILABILITY_MISMATCH"
    PROTOCOL_HASH_MISMATCH = "PROTOCOL_HASH_MISMATCH"
    SPLIT_ORDER_VIOLATION = "SPLIT_ORDER_VIOLATION"
    SPLIT_IDENTITY_VIOLATION = "SPLIT_IDENTITY_VIOLATION"
    TIMEZONE_MISMATCH = "TIMEZONE_MISMATCH"
    TARGET_HISTORY_WITHOUT_LAG = "TARGET_HISTORY_WITHOUT_LAG"


class ValidationIssue(StrictModel):
    code: ValidationIssueCode
    subject: str
    detail: str


class FeatureValidationReport(StrictModel):
    valid: bool
    manifest_id: str
    protocol_hash: str
    checked_feature_count: int = Field(ge=0)
    issues: tuple[ValidationIssue, ...]


class FeatureAvailabilityError(ValueError):
    def __init__(self, report: FeatureValidationReport) -> None:
        summary = "; ".join(f"{issue.code.value}:{issue.subject}" for issue in report.issues)
        super().__init__(f"feature manifest validation failed: {summary}")
        self.report = report


def _revision_unknown(value: str) -> bool:
    return value.strip().lower() in UNKNOWN_REVISIONS


def validate_feature_manifest(manifest: FeatureManifest) -> FeatureValidationReport:
    issues: list[ValidationIssue] = []

    def add(code: ValidationIssueCode, subject: str, detail: str) -> None:
        issues.append(ValidationIssue(code=code, subject=subject, detail=detail))

    if manifest.protocol_hash != manifest.split_manifest.protocol_hash:
        add(
            ValidationIssueCode.PROTOCOL_HASH_MISMATCH,
            manifest.split_manifest.split_id,
            "feature and split manifests must use the same protocol_hash",
        )

    split_rank = {
        DataSplit.TRAIN: 0,
        DataSplit.VALIDATION: 1,
        DataSplit.HOLDOUT: 2,
        DataSplit.PROSPECTIVE: 3,
    }
    windows = manifest.split_manifest.windows
    seen_splits: set[DataSplit] = set()
    previous = None
    for window in windows:
        if window.split in seen_splits:
            add(
                ValidationIssueCode.SPLIT_IDENTITY_VIOLATION,
                window.split.value,
                "a split may appear only once",
            )
        seen_splits.add(window.split)
        if previous is not None:
            if split_rank[window.split] <= split_rank[previous.split]:
                add(
                    ValidationIssueCode.SPLIT_ORDER_VIOLATION,
                    window.split.value,
                    "split order must be TRAIN, VALIDATION, HOLDOUT, PROSPECTIVE",
                )
            if window.start_at < previous.end_at or window.row_start < previous.row_end:
                add(
                    ValidationIssueCode.SPLIT_ORDER_VIOLATION,
                    window.split.value,
                    "split windows must not overlap or move backward",
                )
        previous = window

    if DataSplit.TRAIN not in seen_splits:
        add(
            ValidationIssueCode.SPLIT_IDENTITY_VIOLATION,
            manifest.split_manifest.split_id,
            "TRAIN split is mandatory",
        )

    definition_by_name = {item.feature_name: item for item in manifest.definitions}
    source_by_name = {item.source_name: item for item in manifest.sources}
    availability_by_name = {item.feature_name: item for item in manifest.availabilities}

    identities: set[str] = set()
    feature_names: set[str] = set()
    for definition in manifest.definitions:
        if definition.identity in identities:
            add(
                ValidationIssueCode.DUPLICATE_FEATURE_IDENTITY,
                definition.identity,
                "feature identity must be unique",
            )
        identities.add(definition.identity)
        if definition.feature_name in feature_names:
            add(
                ValidationIssueCode.DUPLICATE_FEATURE_NAME,
                definition.feature_name,
                "feature_name must be unique within one manifest",
            )
        feature_names.add(definition.feature_name)
        if _revision_unknown(definition.revision):
            add(
                ValidationIssueCode.UNKNOWN_REVISION,
                definition.feature_name,
                "feature revision is unknown or mutable",
            )
        if definition.temporal_class is TemporalClass.UNKNOWN:
            add(
                ValidationIssueCode.UNKNOWN_TEMPORAL_CLASS,
                definition.feature_name,
                "temporal_class UNKNOWN is never eligible",
            )
        if definition.temporal_class is TemporalClass.TARGET_HISTORY and definition.lag < 1:
            add(
                ValidationIssueCode.TARGET_HISTORY_WITHOUT_LAG,
                definition.feature_name,
                "TARGET_HISTORY requires lag >= 1",
            )
        if definition.timezone != manifest.timezone:
            add(
                ValidationIssueCode.TIMEZONE_MISMATCH,
                definition.feature_name,
                "feature timezone differs from manifest timezone",
            )

    source_identity_hashes: dict[tuple[str, str], set[str]] = {}
    for source in manifest.sources:
        source_identity_hashes.setdefault((source.source_name, source.revision), set()).add(
            source.source_hash
        )
        if _revision_unknown(source.revision):
            add(
                ValidationIssueCode.UNKNOWN_REVISION,
                source.source_name,
                "source revision is unknown or mutable",
            )
        if source.available_at > manifest.prediction_cutoff:
            add(
                ValidationIssueCode.AVAILABLE_AFTER_PREDICTION_CUTOFF,
                source.source_name,
                "source became available after prediction_cutoff",
            )
        expected = manifest.source_hash_expectations.get(source.source_name)
        if expected is not None and expected != source.source_hash:
            add(
                ValidationIssueCode.SOURCE_HASH_CHANGED,
                source.source_name,
                "source_hash differs from the frozen expectation",
            )
        if source.timezone != manifest.timezone:
            add(
                ValidationIssueCode.TIMEZONE_MISMATCH,
                source.source_name,
                "source timezone differs from manifest timezone",
            )
    for (source_name, revision), hashes in source_identity_hashes.items():
        if len(hashes) > 1:
            add(
                ValidationIssueCode.SOURCE_HASH_CHANGED,
                f"{source_name}@{revision}",
                "one source identity resolves to multiple hashes",
            )

    for availability in manifest.availabilities:
        if availability.available_at > availability.prediction_cutoff:
            add(
                ValidationIssueCode.AVAILABLE_AFTER_PREDICTION_CUTOFF,
                availability.feature_name,
                "feature available_at is later than prediction_cutoff",
            )
        if availability.prediction_cutoff != manifest.prediction_cutoff:
            add(
                ValidationIssueCode.AVAILABILITY_MISMATCH,
                availability.feature_name,
                "availability cutoff differs from manifest cutoff",
            )
        if not availability.known_at_prediction_time:
            add(
                ValidationIssueCode.NOT_KNOWN_AT_PREDICTION_TIME,
                availability.feature_name,
                "known_at_prediction_time must be true",
            )
        if availability.future_target_dependency:
            add(
                ValidationIssueCode.FUTURE_TARGET_DEPENDENCY,
                availability.feature_name,
                "future target dependency is prohibited",
            )
        if availability.temporal_class is TemporalClass.UNKNOWN:
            add(
                ValidationIssueCode.UNKNOWN_TEMPORAL_CLASS,
                availability.feature_name,
                "temporal_class UNKNOWN is never eligible",
            )
        if _revision_unknown(availability.revision):
            add(
                ValidationIssueCode.UNKNOWN_REVISION,
                availability.feature_name,
                "availability revision is unknown or mutable",
            )
        definition = definition_by_name.get(availability.feature_name)
        if definition is None:
            add(
                ValidationIssueCode.DEFINITION_MISMATCH,
                availability.feature_name,
                "availability has no matching FeatureDefinition",
            )
        elif (
            definition.source_name != availability.source_name
            or definition.temporal_class is not availability.temporal_class
            or definition.lag != availability.lag
            or definition.revision != availability.revision
        ):
            add(
                ValidationIssueCode.AVAILABILITY_MISMATCH,
                availability.feature_name,
                "availability does not match its FeatureDefinition",
            )

    materialization_identities: set[str] = set()
    for item in manifest.materializations:
        if item.identity in materialization_identities:
            add(
                ValidationIssueCode.DUPLICATE_FEATURE_IDENTITY,
                item.identity,
                "materialized feature identity must be unique",
            )
        materialization_identities.add(item.identity)
        if item.available_at > item.prediction_cutoff:
            add(
                ValidationIssueCode.AVAILABLE_AFTER_PREDICTION_CUTOFF,
                item.feature_name,
                "materialization became available after prediction_cutoff",
            )
        if item.generated_at > item.prediction_cutoff:
            add(
                ValidationIssueCode.MATERIALIZED_AFTER_PREDICTION_CUTOFF,
                item.feature_name,
                "feature was generated after prediction_cutoff",
            )
        if item.prediction_cutoff != manifest.prediction_cutoff:
            add(
                ValidationIssueCode.AVAILABILITY_MISMATCH,
                item.feature_name,
                "materialization cutoff differs from manifest cutoff",
            )
        if _revision_unknown(item.revision):
            add(
                ValidationIssueCode.UNKNOWN_REVISION,
                item.feature_name,
                "materialization revision is unknown or mutable",
            )
        if item.temporal_class is TemporalClass.UNKNOWN:
            add(
                ValidationIssueCode.UNKNOWN_TEMPORAL_CLASS,
                item.feature_name,
                "temporal_class UNKNOWN is never eligible",
            )
        if not item.known_at_prediction_time:
            add(
                ValidationIssueCode.NOT_KNOWN_AT_PREDICTION_TIME,
                item.feature_name,
                "known_at_prediction_time must be true",
            )
        if item.future_target_dependency:
            add(
                ValidationIssueCode.FUTURE_TARGET_DEPENDENCY,
                item.feature_name,
                "future target dependency is prohibited",
            )
        forbidden_actual_splits = set(item.target_actual_splits) - {DataSplit.TRAIN}
        if forbidden_actual_splits:
            add(
                ValidationIssueCode.POST_TRAIN_ACTUAL_DEPENDENCY,
                item.feature_name,
                "Validation, Holdout, or Prospective actuals were used for feature generation",
            )
        if item.fit_split is not DataSplit.TRAIN:
            add(
                ValidationIssueCode.PREPROCESSOR_FIT_OUTSIDE_TRAIN,
                item.feature_name,
                "materialization fit_split must be TRAIN",
            )
        definition = definition_by_name.get(item.feature_name)
        if definition is None:
            add(
                ValidationIssueCode.DEFINITION_MISMATCH,
                item.feature_name,
                "materialization has no matching FeatureDefinition",
            )
        elif any(
            (
                definition.source_name != item.source_name,
                definition.source_column != item.source_column,
                definition.feature_code_hash != item.feature_code_hash,
                definition.temporal_class is not item.temporal_class,
                definition.lag != item.lag,
                definition.revision != item.revision,
                definition.missing_policy is not item.missing_policy,
            )
        ):
            add(
                ValidationIssueCode.DEFINITION_MISMATCH,
                item.feature_name,
                "materialization does not match its FeatureDefinition",
            )
        source = source_by_name.get(item.source_name)
        if source is None:
            add(
                ValidationIssueCode.SOURCE_REFERENCE_MISMATCH,
                item.feature_name,
                "materialization has no matching FeatureSource",
            )
        elif source.source_hash != item.source_hash or source.revision != item.revision:
            add(
                ValidationIssueCode.SOURCE_REFERENCE_MISMATCH,
                item.feature_name,
                "materialization source hash or revision differs from FeatureSource",
            )
        availability = availability_by_name.get(item.feature_name)
        if availability is None:
            add(
                ValidationIssueCode.AVAILABILITY_MISMATCH,
                item.feature_name,
                "materialization has no matching FeatureAvailability",
            )
        elif availability.available_at != item.available_at:
            add(
                ValidationIssueCode.AVAILABILITY_MISMATCH,
                item.feature_name,
                "materialization available_at differs from FeatureAvailability",
            )
        if item.timezone != manifest.timezone:
            add(
                ValidationIssueCode.TIMEZONE_MISMATCH,
                item.feature_name,
                "materialization timezone differs from manifest timezone",
            )

    for evidence in manifest.preprocessors:
        if evidence.fit_split is not DataSplit.TRAIN:
            add(
                ValidationIssueCode.PREPROCESSOR_FIT_OUTSIDE_TRAIN,
                evidence.preprocessor_name,
                "scaler, encoder, or selector fit_split must be TRAIN",
            )
        if _revision_unknown(evidence.revision):
            add(
                ValidationIssueCode.UNKNOWN_REVISION,
                evidence.preprocessor_name,
                "preprocessor revision is unknown or mutable",
            )
        unknown_features = sorted(set(evidence.feature_names) - set(definition_by_name))
        if unknown_features:
            add(
                ValidationIssueCode.DEFINITION_MISMATCH,
                evidence.preprocessor_name,
                f"preprocessor references unknown features: {unknown_features}",
            )
        if evidence.timezone != manifest.timezone:
            add(
                ValidationIssueCode.TIMEZONE_MISMATCH,
                evidence.preprocessor_name,
                "preprocessor timezone differs from manifest timezone",
            )

    return FeatureValidationReport(
        valid=not issues,
        manifest_id=manifest.manifest_id,
        protocol_hash=manifest.protocol_hash,
        checked_feature_count=len(manifest.definitions),
        issues=tuple(issues),
    )


def assert_feature_manifest_valid(manifest: FeatureManifest) -> FeatureValidationReport:
    report = validate_feature_manifest(manifest)
    if not report.valid:
        raise FeatureAvailabilityError(report)
    return report


__all__ = [
    "FeatureAvailabilityError",
    "FeatureValidationReport",
    "ValidationIssue",
    "ValidationIssueCode",
    "assert_feature_manifest_valid",
    "validate_feature_manifest",
]
