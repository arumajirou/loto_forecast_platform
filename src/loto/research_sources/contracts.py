from __future__ import annotations

from typing import Literal

import re
from pathlib import PurePosixPath

from pydantic import AwareDatetime, BaseModel, ValidationInfo, field_validator, model_validator

from .common import (
    STRICT_CONFIG,
    _FLOATING_VERSION_NAMES,
    _PACKAGE_RE,
    _SENTINELS,
    _SHA256_RE,
    _VERSION_OPERATOR_CHARACTERS,
    _VERSION_SENTINELS,
    CommercialEligibility,
    ContaminationRisk,
    IntakeStatus,
    ReviewStatus,
    _validate_concrete_https_url,
    _validate_nonempty_declaration,
    _validate_sha256,
    _validate_url_or_sentinel,
)

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
        if value in _VERSION_SENTINELS:
            return value
        if value.lower() in _FLOATING_VERSION_NAMES:
            raise ValueError("package version must not use a floating label")
        if any(character in _VERSION_OPERATOR_CHARACTERS for character in value):
            raise ValueError("package version must be one exact version, not a range")
        if "://" in value or value.startswith("git+"):
            raise ValueError("package version must not be a URL or VCS reference")
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
        field_name = info.field_name or "compatibility"
        return _validate_nonempty_declaration(value, field_name)

    @model_validator(mode="after")
    def coherent_compatibility_evidence(self) -> RuntimeCompatibilityDeclaration:
        normalized_names = [
            re.sub(r"[-_.]+", "-", package.name).lower() for package in self.packages
        ]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("duplicate package identity")
        if self.verification_status == "VERIFIED":
            declarations = (self.python, self.torch, self.transformers)
            if any(value in _VERSION_SENTINELS for value in declarations):
                raise ValueError("verified compatibility requires resolved declarations")
            for package in self.packages:
                if package.name in _SENTINELS or package.version in _VERSION_SENTINELS:
                    raise ValueError("verified compatibility requires resolved package identity")
                if package.source in _SENTINELS:
                    raise ValueError("verified compatibility requires resolved package source")
        return self


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
        else:
            if self.review_status == ReviewStatus.REMOTE_CODE_REVIEW_REQUIRED:
                raise ValueError("remote review status conflicts with trust_remote_code=false")
            if self.allowed_files:
                raise ValueError("trust_remote_code=false requires an empty allowed file inventory")
            if self.review_status == ReviewStatus.VERIFIED and (
                self.policy_id in _SENTINELS or not self.policy_id.strip()
            ):
                raise ValueError("verified remote-code review requires a concrete policy id")
        return self


class ContaminationDeclaration(BaseModel):
    model_config = STRICT_CONFIG

    pretraining_disclosure: str
    benchmark_contamination_risk: ContaminationRisk
    benchmark_names: tuple[str, ...]
    evidence_status: Literal["UNKNOWN", "UNVERIFIED", "VERIFIED"]

    @field_validator("pretraining_disclosure")
    @classmethod
    def nonempty_disclosure(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("pretraining_disclosure must be non-empty")
        return value

    @field_validator("benchmark_names")
    @classmethod
    def valid_benchmark_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate benchmark name")
        if any(not value or value != value.strip() for value in values):
            raise ValueError("benchmark names must be non-empty and trimmed")
        return values

    @model_validator(mode="after")
    def coherent_contamination_evidence(self) -> ContaminationDeclaration:
        if self.evidence_status == "VERIFIED":
            if self.pretraining_disclosure in _SENTINELS:
                raise ValueError("verified contamination evidence requires a disclosure")
            if self.benchmark_contamination_risk == ContaminationRisk.UNKNOWN:
                raise ValueError("verified contamination evidence requires resolved risk")
        return self


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
        if len(values) != len(set(values)):
            raise ValueError("duplicate official URL evidence")
        for value in values:
            _validate_url_or_sentinel(value)
        return values

    @field_validator("findings", "blockers")
    @classmethod
    def validate_evidence_notes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate verification evidence note")
        if any(not value or value != value.strip() for value in values):
            raise ValueError("verification evidence notes must be non-empty and trimmed")
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

