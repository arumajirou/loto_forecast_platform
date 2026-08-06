from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

STRICT_CONFIG = ConfigDict(
    extra="forbid",
    strict=True,
    allow_inf_nan=False,
    validate_assignment=True,
)

_SENTINELS = {
    "UNKNOWN",
    "UNPINNED",
    "UNVERIFIED",
    "LICENSE_REVIEW_REQUIRED",
    "REMOTE_CODE_REVIEW_REQUIRED",
    "NOT_RELEASED",
}
_SHA_SENTINELS = {"UNKNOWN", "UNVERIFIED", "NOT_RELEASED"}
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PACKAGE_RE = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
_VERSION_SENTINELS = {"UNKNOWN", "UNPINNED", "UNVERIFIED", "NOT_RELEASED"}
_FLOATING_VERSION_NAMES = {"dev", "head", "latest", "main", "master", "nightly"}


class IntakeStatus(str, Enum):
    VERIFIED_FOR_INTAKE = "VERIFIED_FOR_INTAKE"
    CONDITIONAL = "CONDITIONAL"
    REMOTE_CODE_REVIEW_REQUIRED = "REMOTE_CODE_REVIEW_REQUIRED"
    LICENSE_REVIEW_REQUIRED = "LICENSE_REVIEW_REQUIRED"
    CHECKPOINT_REVIEW_REQUIRED = "CHECKPOINT_REVIEW_REQUIRED"
    NOT_RELEASED = "NOT_RELEASED"
    BLOCKED = "BLOCKED"


class SourceKind(str, Enum):
    MODEL = "MODEL"
    METHOD = "METHOD"


class ReleaseStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_RELEASED = "NOT_RELEASED"
    UNKNOWN = "UNKNOWN"


class CommercialEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"
    LICENSE_REVIEW_REQUIRED = "LICENSE_REVIEW_REQUIRED"


class ReviewStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    REMOTE_CODE_REVIEW_REQUIRED = "REMOTE_CODE_REVIEW_REQUIRED"


class ContaminationRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


def _validate_identifier(value: str, field_name: str) -> str:
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be lowercase kebab/dot/underscore identifier")
    return value


def _validate_concrete_https_url(value: str) -> str:
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise ValueError("URL must not contain whitespace or control characters")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("URL must use https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not contain credentials")
    return value


def _validate_url_or_sentinel(value: str) -> str:
    if value in _SENTINELS:
        return value
    return _validate_concrete_https_url(value)


def _validate_nonempty_declaration(value: str, field_name: str) -> str:
    if value in _VERSION_SENTINELS:
        return value
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty or an explicit sentinel")
    return value


def _validate_revision(value: str) -> str:
    if value in _SENTINELS:
        return value
    if not _REVISION_RE.fullmatch(value):
        raise ValueError("revision must be a lowercase 40-character commit or explicit sentinel")
    return value


def _validate_sha256(value: str) -> str:
    if value in _SHA_SENTINELS:
        return value
    if not _SHA256_RE.fullmatch(value):
        raise ValueError("sha256 must be lowercase hexadecimal or explicit sentinel")
    return value


class RepositoryIdentity(BaseModel):
    model_config = STRICT_CONFIG

    url: str
    repository_type: Literal["source", "model", "model_and_code", "mirror"]
    official: bool
    canonical: bool
    mirror: bool

    _url = field_validator("url")(_validate_concrete_https_url)

    @model_validator(mode="after")
    def canonical_is_official(self) -> RepositoryIdentity:
        if self.canonical and (not self.official or self.mirror):
            raise ValueError("canonical repository must be official and must not be a mirror")
        if self.repository_type == "mirror" and not self.mirror:
            raise ValueError("mirror repository_type requires mirror=true")
        if self.mirror and self.repository_type != "mirror":
            raise ValueError("mirror=true requires repository_type=mirror")
        return self


class ArtifactIdentity(BaseModel):
    model_config = STRICT_CONFIG

    path: str
    required: bool
    size_bytes: int | Literal["UNKNOWN", "UNVERIFIED", "NOT_RELEASED"]
    sha256: str

    @field_validator("path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        if not value or "\\" in value or value.startswith("./") or "//" in value:
            raise ValueError("artifact path must be a non-empty POSIX relative path")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("artifact path must not be absolute or contain traversal")
        return value

    @field_validator("size_bytes")
    @classmethod
    def nonnegative_size(
        cls, value: int | Literal["UNKNOWN", "UNVERIFIED", "NOT_RELEASED"]
    ) -> int | Literal["UNKNOWN", "UNVERIFIED", "NOT_RELEASED"]:
        if isinstance(value, int) and value < 0:
            raise ValueError("size_bytes must be non-negative")
        return value

    _sha = field_validator("sha256")(_validate_sha256)


class PackageIdentity(BaseModel):
    model_config = STRICT_CONFIG

    name: str
    version: str
    source: str

    @field_validator("name")
    @classmethod
    def valid_package_name(cls, value: str) -> str:
        if value not in _SENTINELS and not _PACKAGE_RE.fullmatch(value):
            raise ValueError("invalid package name")
        return value

    @field_validator("version")
    @classmethod
    def fixed_or_explicit_version(cls, value: str) -> str:
        value = _validate_nonempty_declaration(value, "package version")
        if value.lower() in _FLOATING_VERSION_NAMES:
            raise ValueError("package version must not use a floating label")
        return value

    _source = field_validator("source")(_validate_url_or_sentinel)


class LicenseBoundary(BaseModel):
    model_config = STRICT_CONFIG

    code_license: str
    weight_license: str
    code_license_source: str
    weight_license_source: str
    commercial_eligibility: CommercialEligibility

    _code_source = field_validator("code_license_source")(_validate_url_or_sentinel)
    _weight_source = field_validator("weight_license_source")(_validate_url_or_sentinel)

    @model_validator(mode="after")
    def separated_licenses(self) -> LicenseBoundary:
        if not self.code_license.strip() or not self.weight_license.strip():
            raise ValueError("code and weight license fields must be separately populated")
        return self


class RuntimeCompatibilityDeclaration(BaseModel):
    model_config = STRICT_CONFIG

    python: str
    torch: str
    transformers: str
    packages: tuple[PackageIdentity, ...]
    verification_status: Literal["UNKNOWN", "UNVERIFIED", "VERIFIED"]

    @field_validator("python", "torch", "transformers")
    @classmethod
    def explicit_compatibility(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name
        return _validate_nonempty_declaration(value, field_name)


class RemoteCodePolicy(BaseModel):
    model_config = STRICT_CONFIG

    trust_remote_code: bool
    review_status: ReviewStatus
    policy_id: str
    allowed_files: tuple[str, ...]

    @field_validator("allowed_files")
    @classmethod
    def validate_allowed_files(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate remote-code allowed file")
        for value in values:
            ArtifactIdentity.safe_relative_path(value)
        return values

    @model_validator(mode="after")
    def required_review_policy(self) -> RemoteCodePolicy:
        if self.trust_remote_code:
            if self.review_status not in {
                ReviewStatus.REMOTE_CODE_REVIEW_REQUIRED,
                ReviewStatus.VERIFIED,
            }:
                raise ValueError("remote code requires an explicit review status")
            if self.policy_id in _SENTINELS or not self.policy_id.strip():
                raise ValueError("remote code requires a concrete review policy id")
            if self.review_status == ReviewStatus.VERIFIED and not self.allowed_files:
                raise ValueError("verified remote code requires a non-empty allowed file inventory")
        elif self.review_status == ReviewStatus.REMOTE_CODE_REVIEW_REQUIRED:
            raise ValueError("remote review status conflicts with trust_remote_code=false")
        return self


class ContaminationDeclaration(BaseModel):
    model_config = STRICT_CONFIG

    pretraining_disclosure: str
    benchmark_contamination_risk: ContaminationRisk
    benchmark_names: tuple[str, ...]
    evidence_status: Literal["UNKNOWN", "UNVERIFIED", "VERIFIED"]


class SourceVerificationReport(BaseModel):
    model_config = STRICT_CONFIG

    checked_at: AwareDatetime
    status: IntakeStatus
    verification_method: str
    official_urls_checked: tuple[str, ...]
    findings: tuple[str, ...]
    blockers: tuple[str, ...]

    @field_validator("verification_method")
    @classmethod
    def nonempty_method(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("verification_method must be non-empty")
        return value

    @field_validator("official_urls_checked")
    @classmethod
    def validate_urls(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _validate_url_or_sentinel(value)
        return values


class NonClaims(BaseModel):
    model_config = STRICT_CONFIG

    runtime_success: bool = False
    production_eligibility: bool = False
    model_implemented: bool = False
    dependency_resolution_executed: bool = False
    checkpoint_download_executed: bool = False
    cpu_gpu_runtime_executed: bool = False
    oof_executed: bool = False
    holdout_opened: bool = False
    prospective_opened: bool = False
    production_registration_performed: bool = False

    @model_validator(mode="after")
    def all_claims_false(self) -> NonClaims:
        if any(self.model_dump().values()):
            raise ValueError(
                "Research Source Registry records cannot claim execution or eligibility"
            )
        return self


class ResearchSourceRecord(BaseModel):
    model_config = STRICT_CONFIG

    source_id: str
    logical_model_id: str
    source_kind: SourceKind
    paper_title: str
    paper_identifier: str
    paper_published_on: str
    official_paper_url: str
    official_source_repository: RepositoryIdentity | Literal["UNKNOWN", "NOT_RELEASED"]
    source_revision: str
    official_model_repository: RepositoryIdentity | Literal["UNKNOWN", "NOT_RELEASED"]
    model_revision: str
    required_files: tuple[ArtifactIdentity, ...]
    runtime_compatibility: RuntimeCompatibilityDeclaration
    license_boundary: LicenseBoundary
    remote_code_policy: RemoteCodePolicy
    contamination: ContaminationDeclaration
    release_status: ReleaseStatus
    verification: SourceVerificationReport
    superseded_by_source_id: str | None = None
    non_claims: NonClaims = Field(default_factory=NonClaims)

    @field_validator("source_id")
    @classmethod
    def valid_source_id(cls, value: str) -> str:
        return _validate_identifier(value, "source_id")

    @field_validator("logical_model_id")
    @classmethod
    def valid_model_id(cls, value: str) -> str:
        return _validate_identifier(value, "logical_model_id")

    @field_validator("paper_published_on")
    @classmethod
    def valid_date(cls, value: str) -> str:
        if value not in {"UNKNOWN", "NOT_RELEASED"}:
            if not _DATE_RE.fullmatch(value):
                raise ValueError("paper_published_on must be YYYY-MM-DD or explicit sentinel")
            datetime.strptime(value, "%Y-%m-%d")
        return value

    _paper_url = field_validator("official_paper_url")(_validate_url_or_sentinel)
    _source_revision = field_validator("source_revision")(_validate_revision)
    _model_revision = field_validator("model_revision")(_validate_revision)

    @field_validator("superseded_by_source_id")
    @classmethod
    def valid_superseded_id(cls, value: str | None) -> str | None:
        if value is not None:
            return _validate_identifier(value, "superseded_by_source_id")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> ResearchSourceRecord:
        paths = [artifact.path for artifact in self.required_files]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate artifact path")
        if self.release_status == ReleaseStatus.NOT_RELEASED and self.verification.status not in {
            IntakeStatus.NOT_RELEASED,
            IntakeStatus.BLOCKED,
        }:
            raise ValueError("not-released source cannot be marked available for intake")
        if self.verification.status == IntakeStatus.VERIFIED_FOR_INTAKE:
            if self.release_status != ReleaseStatus.AVAILABLE:
                raise ValueError("verified intake requires release_status=AVAILABLE")
            if not isinstance(self.official_source_repository, RepositoryIdentity):
                raise ValueError("verified formal source requires a concrete source repository")
            if self.source_revision in _SENTINELS:
                raise ValueError("verified formal source must pin source_revision")
            if self.source_kind == SourceKind.MODEL:
                if not isinstance(self.official_model_repository, RepositoryIdentity):
                    raise ValueError("verified model intake requires a concrete model repository")
                if self.model_revision in _SENTINELS:
                    raise ValueError("verified model intake must pin model_revision")
                required_artifacts = [
                    artifact for artifact in self.required_files if artifact.required
                ]
                if not required_artifacts:
                    raise ValueError("verified model intake requires required artifact inventory")
                for artifact in required_artifacts:
                    if not isinstance(artifact.size_bytes, int):
                        raise ValueError("verified intake requires required artifact sizes")
                    if not _SHA256_RE.fullmatch(artifact.sha256):
                        raise ValueError(
                            "verified intake requires required artifact SHA-256 values"
                        )
            unresolved_licenses = _SENTINELS | {""}
            if self.license_boundary.code_license in unresolved_licenses:
                raise ValueError("verified intake requires resolved code license")
            if self.license_boundary.weight_license in unresolved_licenses:
                raise ValueError("verified intake requires resolved weight license")
            if self.license_boundary.code_license_source in _SENTINELS:
                raise ValueError("verified intake requires resolved code license source")
            if self.license_boundary.weight_license_source in _SENTINELS:
                raise ValueError("verified intake requires resolved weight license source")
            if self.license_boundary.commercial_eligibility in {
                CommercialEligibility.UNKNOWN,
                CommercialEligibility.LICENSE_REVIEW_REQUIRED,
            }:
                raise ValueError("verified intake requires resolved commercial eligibility")
            if self.verification.blockers:
                raise ValueError("verified intake cannot retain unresolved blockers")

        if self.remote_code_policy.trust_remote_code:
            if self.remote_code_policy.review_status != ReviewStatus.VERIFIED:
                if self.verification.status not in {
                    IntakeStatus.REMOTE_CODE_REVIEW_REQUIRED,
                    IntakeStatus.LICENSE_REVIEW_REQUIRED,
                    IntakeStatus.BLOCKED,
                }:
                    raise ValueError("unreviewed remote code cannot be promoted to intake")
            else:
                artifact_by_path = {artifact.path: artifact for artifact in self.required_files}
                for allowed_file in self.remote_code_policy.allowed_files:
                    artifact = artifact_by_path.get(allowed_file)
                    if artifact is None:
                        raise ValueError("reviewed remote file must exist in artifact inventory")
                    if not isinstance(artifact.size_bytes, int) or not _SHA256_RE.fullmatch(
                        artifact.sha256
                    ):
                        raise ValueError("reviewed remote file requires pinned size and SHA-256")
        if self.superseded_by_source_id == self.source_id:
            raise ValueError("source cannot supersede itself")
        return self


class ResearchSourceRegistry(BaseModel):
    model_config = STRICT_CONFIG

    schema_version: Literal["1.0.0"]
    generated_at: AwareDatetime
    records: tuple[ResearchSourceRecord, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> ResearchSourceRegistry:
        source_ids = [record.source_id for record in self.records]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source_id")
        model_ids = [record.logical_model_id for record in self.records]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("duplicate logical model_id")

        records_by_id = {record.source_id: record for record in self.records}
        for record in self.records:
            target = record.superseded_by_source_id
            if target is not None and target not in records_by_id:
                raise ValueError(f"unknown superseded target: {target}")

        for start in source_ids:
            seen: set[str] = set()
            current: str | None = start
            while current is not None:
                if current in seen:
                    raise ValueError("superseded revision cycle detected")
                seen.add(current)
                current = records_by_id[current].superseded_by_source_id
        return self
