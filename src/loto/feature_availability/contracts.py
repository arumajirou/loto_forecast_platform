"""Strict contracts for prediction-time feature availability evidence."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
UNKNOWN_REVISIONS = frozenset({"unknown", "unversioned", "unpinned", "latest", "none", "n/a"})


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )


class TemporalClass(StrEnum):
    TARGET_HISTORY = "TARGET_HISTORY"
    PAST_ONLY = "PAST_ONLY"
    KNOWN_FUTURE = "KNOWN_FUTURE"
    STATIC = "STATIC"
    UNKNOWN = "UNKNOWN"


class DataSplit(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    HOLDOUT = "HOLDOUT"
    PROSPECTIVE = "PROSPECTIVE"


class MissingPolicy(StrEnum):
    ERROR = "ERROR"
    DROP_ROW = "DROP_ROW"
    IMPUTE_TRAIN_ONLY = "IMPUTE_TRAIN_ONLY"
    FORWARD_FILL_PAST_ONLY = "FORWARD_FILL_PAST_ONLY"
    ALLOW_NULL = "ALLOW_NULL"


class PreprocessorKind(StrEnum):
    SCALER = "SCALER"
    ENCODER = "ENCODER"
    SELECTOR = "SELECTOR"
    OTHER = "OTHER"


def _validate_name(value: str) -> str:
    if not SAFE_NAME_PATTERN.fullmatch(value):
        raise ValueError("must be a safe non-empty identity")
    return value


def _validate_sha256(value: str) -> str:
    if not SHA256_PATTERN.fullmatch(value):
        raise ValueError("must be a lowercase SHA-256 hex digest")
    return value


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return value


def _validate_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class FeatureDefinition(StrictModel):
    feature_name: str
    source_name: str
    source_column: str
    feature_code_hash: str
    temporal_class: TemporalClass
    lag: int = Field(ge=0)
    timezone: str
    revision: str = Field(min_length=1, max_length=255)
    missing_policy: MissingPolicy

    _feature_name = field_validator("feature_name")(_validate_name)
    _source_name = field_validator("source_name")(_validate_name)
    _source_column = field_validator("source_column")(_validate_name)
    _feature_code_hash = field_validator("feature_code_hash")(_validate_sha256)
    _timezone = field_validator("timezone")(_validate_timezone)

    @model_validator(mode="after")
    def validate_lag_semantics(self) -> FeatureDefinition:
        if self.temporal_class is TemporalClass.TARGET_HISTORY and self.lag < 1:
            raise ValueError("TARGET_HISTORY requires lag >= 1")
        return self

    @property
    def identity(self) -> str:
        return "|".join(
            (
                self.feature_name,
                self.source_name,
                self.source_column,
                self.revision,
                self.feature_code_hash,
            )
        )


class FeatureSource(StrictModel):
    source_name: str
    source_hash: str
    generated_at: datetime
    available_at: datetime
    timezone: str
    revision: str = Field(min_length=1, max_length=255)

    _source_name = field_validator("source_name")(_validate_name)
    _source_hash = field_validator("source_hash")(_validate_sha256)
    _timezone = field_validator("timezone")(_validate_timezone)
    _generated_at = field_validator("generated_at")(_validate_aware)
    _available_at = field_validator("available_at")(_validate_aware)


class FeatureAvailability(StrictModel):
    feature_name: str
    source_name: str
    available_at: datetime
    prediction_cutoff: datetime
    temporal_class: TemporalClass
    lag: int = Field(ge=0)
    timezone: str
    known_at_prediction_time: bool
    future_target_dependency: bool
    revision: str = Field(min_length=1, max_length=255)

    _feature_name = field_validator("feature_name")(_validate_name)
    _source_name = field_validator("source_name")(_validate_name)
    _timezone = field_validator("timezone")(_validate_timezone)
    _available_at = field_validator("available_at")(_validate_aware)
    _prediction_cutoff = field_validator("prediction_cutoff")(_validate_aware)


class FeatureMaterialization(StrictModel):
    feature_name: str
    source_name: str
    source_hash: str
    source_column: str
    feature_code_hash: str
    generated_at: datetime
    available_at: datetime
    prediction_cutoff: datetime
    temporal_class: TemporalClass
    lag: int = Field(ge=0)
    timezone: str
    fit_split: DataSplit
    transform_split: DataSplit
    known_at_prediction_time: bool
    future_target_dependency: bool
    revision: str = Field(min_length=1, max_length=255)
    missing_policy: MissingPolicy
    target_actual_splits: tuple[DataSplit, ...] = ()
    materialization_hash: str

    _feature_name = field_validator("feature_name")(_validate_name)
    _source_name = field_validator("source_name")(_validate_name)
    _source_column = field_validator("source_column")(_validate_name)
    _source_hash = field_validator("source_hash")(_validate_sha256)
    _feature_code_hash = field_validator("feature_code_hash")(_validate_sha256)
    _materialization_hash = field_validator("materialization_hash")(_validate_sha256)
    _timezone = field_validator("timezone")(_validate_timezone)
    _generated_at = field_validator("generated_at")(_validate_aware)
    _available_at = field_validator("available_at")(_validate_aware)
    _prediction_cutoff = field_validator("prediction_cutoff")(_validate_aware)

    @property
    def identity(self) -> str:
        return "|".join(
            (
                self.feature_name,
                self.source_name,
                self.source_column,
                self.revision,
                self.feature_code_hash,
            )
        )


class PreprocessorFitEvidence(StrictModel):
    preprocessor_name: str
    preprocessor_kind: PreprocessorKind
    feature_names: tuple[str, ...] = Field(min_length=1)
    fit_split: DataSplit
    transform_split: DataSplit
    fit_data_hash: str
    preprocessor_code_hash: str
    fitted_at: datetime
    timezone: str
    revision: str = Field(min_length=1, max_length=255)

    _preprocessor_name = field_validator("preprocessor_name")(_validate_name)
    _fit_data_hash = field_validator("fit_data_hash")(_validate_sha256)
    _preprocessor_code_hash = field_validator("preprocessor_code_hash")(_validate_sha256)
    _timezone = field_validator("timezone")(_validate_timezone)
    _fitted_at = field_validator("fitted_at")(_validate_aware)

    @field_validator("feature_names")
    @classmethod
    def validate_feature_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("feature_names must be unique")
        return tuple(_validate_name(item) for item in value)


class SplitWindow(StrictModel):
    split: DataSplit
    start_at: datetime
    end_at: datetime
    row_start: int = Field(ge=0)
    row_end: int = Field(gt=0)

    _start_at = field_validator("start_at")(_validate_aware)
    _end_at = field_validator("end_at")(_validate_aware)

    @model_validator(mode="after")
    def validate_bounds(self) -> SplitWindow:
        if self.start_at >= self.end_at:
            raise ValueError("split start_at must be earlier than end_at")
        if self.row_start >= self.row_end:
            raise ValueError("split row_start must be smaller than row_end")
        return self


class SplitManifest(StrictModel):
    schema_version: str = "1.0.0"
    split_id: str
    protocol_hash: str
    generated_at: datetime
    timezone: str
    windows: tuple[SplitWindow, ...] = Field(min_length=1)

    _split_id = field_validator("split_id")(_validate_name)
    _protocol_hash = field_validator("protocol_hash")(_validate_sha256)
    _timezone = field_validator("timezone")(_validate_timezone)
    _generated_at = field_validator("generated_at")(_validate_aware)


class FeatureManifest(StrictModel):
    schema_version: str = "1.0.0"
    manifest_id: str
    protocol_hash: str
    generated_at: datetime
    prediction_cutoff: datetime
    timezone: str
    definitions: tuple[FeatureDefinition, ...] = Field(min_length=1)
    sources: tuple[FeatureSource, ...] = Field(min_length=1)
    availabilities: tuple[FeatureAvailability, ...] = Field(min_length=1)
    materializations: tuple[FeatureMaterialization, ...] = Field(min_length=1)
    preprocessors: tuple[PreprocessorFitEvidence, ...] = ()
    split_manifest: SplitManifest
    source_hash_expectations: dict[str, str] = Field(default_factory=dict)

    _manifest_id = field_validator("manifest_id")(_validate_name)
    _protocol_hash = field_validator("protocol_hash")(_validate_sha256)
    _timezone = field_validator("timezone")(_validate_timezone)
    _generated_at = field_validator("generated_at")(_validate_aware)
    _prediction_cutoff = field_validator("prediction_cutoff")(_validate_aware)

    @field_validator("source_hash_expectations")
    @classmethod
    def validate_source_hash_expectations(cls, value: dict[str, str]) -> dict[str, str]:
        return {_validate_name(key): _validate_sha256(item) for key, item in value.items()}


__all__ = [
    "DataSplit",
    "FeatureAvailability",
    "FeatureDefinition",
    "FeatureManifest",
    "FeatureMaterialization",
    "FeatureSource",
    "MissingPolicy",
    "PreprocessorFitEvidence",
    "PreprocessorKind",
    "SplitManifest",
    "SplitWindow",
    "TemporalClass",
    "UNKNOWN_REVISIONS",
]
