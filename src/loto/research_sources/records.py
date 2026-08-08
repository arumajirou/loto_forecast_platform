from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import (
    _DATE_RE,
    _SENTINELS,
    _SHA256_RE,
    _VERSION_SENTINELS,
    STRICT_CONFIG,
    CommercialEligibility,
    ContaminationRisk,
    IntakeStatus,
    ReleaseStatus,
    ReviewStatus,
    SourceKind,
    _validate_identifier,
    _validate_revision,
    _validate_url_or_sentinel,
)
from .contracts import (
    ArtifactIdentity,
    ContaminationDeclaration,
    LicenseBoundary,
    NonClaims,
    RemoteCodePolicy,
    RepositoryIdentity,
    RuntimeCompatibilityDeclaration,
    SourceVerificationReport,
)


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

    @field_validator("paper_title", "paper_identifier")
    @classmethod
    def nonempty_paper_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("paper identity fields must be non-empty")
        return value

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
        if (
            self.verification.status == IntakeStatus.NOT_RELEASED
            and self.release_status != ReleaseStatus.NOT_RELEASED
        ):
            raise ValueError("NOT_RELEASED intake status requires release_status=NOT_RELEASED")
        if self.verification.status == IntakeStatus.REMOTE_CODE_REVIEW_REQUIRED and not (
            self.remote_code_policy.trust_remote_code
            and self.remote_code_policy.review_status == ReviewStatus.REMOTE_CODE_REVIEW_REQUIRED
        ):
            raise ValueError("remote-code intake status requires a pending remote-code review")
        if self.verification.status == IntakeStatus.VERIFIED_FOR_INTAKE:
            if self.release_status != ReleaseStatus.AVAILABLE:
                raise ValueError("verified intake requires release_status=AVAILABLE")
            if (
                self.official_paper_url in _SENTINELS
                or self.paper_title in _SENTINELS
                or self.paper_identifier in _SENTINELS
                or self.paper_published_on in {"UNKNOWN", "NOT_RELEASED"}
            ):
                raise ValueError("verified intake requires concrete paper identity")
            if not isinstance(self.official_source_repository, RepositoryIdentity):
                raise ValueError("verified formal source requires a concrete source repository")
            if not (
                self.official_source_repository.official
                and self.official_source_repository.canonical
                and not self.official_source_repository.mirror
            ):
                raise ValueError("verified source repository must be canonical and official")
            if self.official_source_repository.repository_type not in {
                "source",
                "model_and_code",
            }:
                raise ValueError("verified source repository has an invalid repository type")
            if self.source_revision in _SENTINELS:
                raise ValueError("verified formal source must pin source_revision")
            if self.source_kind == SourceKind.MODEL:
                if not isinstance(self.official_model_repository, RepositoryIdentity):
                    raise ValueError("verified model intake requires a concrete model repository")
                if not (
                    self.official_model_repository.official
                    and self.official_model_repository.canonical
                    and not self.official_model_repository.mirror
                ):
                    raise ValueError("verified model repository must be canonical and official")
                if self.official_model_repository.repository_type not in {
                    "model",
                    "model_and_code",
                }:
                    raise ValueError("verified model repository has an invalid repository type")
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
                if not self.runtime_compatibility.packages:
                    raise ValueError("verified model intake requires package identity")
            if self.runtime_compatibility.verification_status != "VERIFIED":
                raise ValueError("verified intake requires verified runtime compatibility")
            compatibility_values = (
                self.runtime_compatibility.python,
                self.runtime_compatibility.torch,
                self.runtime_compatibility.transformers,
            )
            if any(value in _VERSION_SENTINELS for value in compatibility_values):
                raise ValueError("verified intake requires resolved compatibility declarations")
            for package in self.runtime_compatibility.packages:
                if (
                    package.name in _SENTINELS
                    or package.version in _VERSION_SENTINELS
                    or package.source in _SENTINELS
                ):
                    raise ValueError("verified intake requires resolved package identity")
            if (
                self.contamination.evidence_status != "VERIFIED"
                or self.contamination.pretraining_disclosure in _SENTINELS
                or self.contamination.benchmark_contamination_risk == ContaminationRisk.UNKNOWN
            ):
                raise ValueError("verified intake requires resolved contamination evidence")
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
            if not self.verification.official_urls_checked:
                raise ValueError("verified intake requires official URL verification evidence")
            checked_urls = set(self.verification.official_urls_checked)
            expected_urls = {
                self.official_paper_url,
                self.official_source_repository.url,
                self.license_boundary.code_license_source,
                self.license_boundary.weight_license_source,
            }
            if isinstance(self.official_model_repository, RepositoryIdentity):
                expected_urls.add(self.official_model_repository.url)
            expected_urls.update(package.source for package in self.runtime_compatibility.packages)
            if not expected_urls <= checked_urls:
                raise ValueError("verified intake is missing official URL verification evidence")
            if not self.remote_code_policy.trust_remote_code and (
                self.remote_code_policy.review_status
                not in {ReviewStatus.NOT_REQUIRED, ReviewStatus.VERIFIED}
            ):
                raise ValueError("verified intake requires a resolved remote-code policy")

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
                    if not artifact.required:
                        raise ValueError("reviewed remote file must be a required artifact")
                    if not isinstance(artifact.size_bytes, int) or not _SHA256_RE.fullmatch(
                        artifact.sha256
                    ):
                        raise ValueError("reviewed remote file requires pinned size and SHA-256")
        if self.superseded_by_source_id == self.source_id:
            raise ValueError("source cannot supersede itself")
        return self
