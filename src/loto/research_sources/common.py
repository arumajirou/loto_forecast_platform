from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import ConfigDict

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
_VERSION_OPERATOR_CHARACTERS = frozenset("<>=!~*,^|&")


class IntakeStatus(StrEnum):
    VERIFIED_FOR_INTAKE = "VERIFIED_FOR_INTAKE"
    CONDITIONAL = "CONDITIONAL"
    REMOTE_CODE_REVIEW_REQUIRED = "REMOTE_CODE_REVIEW_REQUIRED"
    LICENSE_REVIEW_REQUIRED = "LICENSE_REVIEW_REQUIRED"
    CHECKPOINT_REVIEW_REQUIRED = "CHECKPOINT_REVIEW_REQUIRED"
    NOT_RELEASED = "NOT_RELEASED"
    BLOCKED = "BLOCKED"


class SourceKind(StrEnum):
    MODEL = "MODEL"
    METHOD = "METHOD"


class ReleaseStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_RELEASED = "NOT_RELEASED"
    UNKNOWN = "UNKNOWN"


class CommercialEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"
    LICENSE_REVIEW_REQUIRED = "LICENSE_REVIEW_REQUIRED"


class ReviewStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    REMOTE_CODE_REVIEW_REQUIRED = "REMOTE_CODE_REVIEW_REQUIRED"


class ContaminationRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


def _validate_identifier(value: str, field_name: str) -> str:
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be lowercase kebab/dot/underscore identifier")
    return value


def _validate_concrete_https_url(value: str) -> str:
    if value != value.strip() or any(
        character.isspace() or ord(character) < 32 for character in value
    ):
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
