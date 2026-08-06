from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

MODEL_ID = "timer-base-84m"
REPO_ID = "thuml/timer-base-84m"
MODEL_REVISION = "70077a71acce1b4c00d98332fcaabc694255d8e5"
CONFIG_SHA256 = "UNVERIFIED"
WEIGHT_SHA256 = "9c3d18f12ffe1ea7d4fa70eb3304b26e3841164a6a265fbae4f7a05cd213aa3d"
SOURCE_REPOSITORY = "https://github.com/thuml/Large-Time-Series-Model"
SOURCE_REVISION = "UNPINNED"
OBSERVED_SOURCE_HEAD = "1ff8d1afc073182e6d46022069ff32470ab47945"
TRANSFORMERS_VERSION = "4.40.1"
PYTHON_LANE = ">=3.10,<3.11"
LICENSE = "Apache-2.0"
EXPECTED_SNAPSHOT_FILES = frozenset(
    {
        "README.md",
        "config.json",
        "configuration_timer.py",
        "generation_config.json",
        "model.safetensors",
        "modeling_timer.py",
        "ts_generation_mixin.py",
    }
)
EXPECTED_REMOTE_CODE_FILES = (
    "configuration_timer.py",
    "modeling_timer.py",
    "ts_generation_mixin.py",
)
EXPECTED_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "review_status",
        "approved",
        "trust_remote_code_allowed",
        "reviewer",
        "reviewed_at_utc",
        "repo_id",
        "model_revision",
        "source_repository",
        "source_revision",
        "observed_source_head",
        "license",
        "license_file_status",
        "remote_code_files",
        "files",
        "review_notes",
    }
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ProvenanceError(ValueError):
    pass


def _reject_non_json_constant(value: str) -> None:
    raise ProvenanceError(f"non-JSON numeric constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_review(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_json_constant,
    )
    if not isinstance(payload, dict):
        raise ProvenanceError("remote-code review must be a JSON object")
    return payload


def _validate_reviewed_at_utc(value: Any) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ProvenanceError("approved review must record reviewed_at_utc")
    if not value.endswith("+00:00"):
        raise ProvenanceError("reviewed_at_utc must be timezone-aware UTC")
    try:
        reviewed_at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ProvenanceError("reviewed_at_utc must be valid ISO-8601") from exc
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() != timedelta(0):
        raise ProvenanceError("reviewed_at_utc must be timezone-aware UTC")


def validate_remote_code_review(review: dict[str, Any]) -> None:
    if not isinstance(review, dict):
        raise ProvenanceError("remote-code review must be a JSON object")
    fields = frozenset(review)
    if fields != EXPECTED_REVIEW_FIELDS:
        missing = sorted(EXPECTED_REVIEW_FIELDS - fields)
        unknown = sorted(fields - EXPECTED_REVIEW_FIELDS)
        raise ProvenanceError(
            f"remote-code review fields mismatch: missing={missing}, unknown={unknown}"
        )

    expected_identity = {
        "schema_version": "timer-base-84m.remote-code-review.v1",
        "repo_id": REPO_ID,
        "model_revision": MODEL_REVISION,
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": SOURCE_REVISION,
        "observed_source_head": OBSERVED_SOURCE_HEAD,
        "license": LICENSE,
        "license_file_status": "NOT_PRESENT_IN_MODEL_SNAPSHOT",
    }
    for field, expected in expected_identity.items():
        if review.get(field) != expected:
            raise ProvenanceError(f"remote-code review {field} mismatch")

    notes = review.get("review_notes")
    if (
        not isinstance(notes, list)
        or not notes
        or any(not isinstance(note, str) or not note.strip() for note in notes)
    ):
        raise ProvenanceError("remote-code review notes must be non-empty strings")

    files = review.get("files")
    if not isinstance(files, dict) or frozenset(files) != EXPECTED_SNAPSHOT_FILES:
        raise ProvenanceError("snapshot file allowlist mismatch")
    remote_code_files = review.get("remote_code_files")
    if remote_code_files != list(EXPECTED_REMOTE_CODE_FILES):
        raise ProvenanceError("remote-code execution allowlist mismatch")
    if files.get("model.safetensors") != WEIGHT_SHA256:
        raise ProvenanceError("model weight hash mismatch")
    if CONFIG_SHA256 != "UNVERIFIED" and files.get("config.json") != CONFIG_SHA256:
        raise ProvenanceError("config hash mismatch")

    unresolved = [
        name for name, digest in files.items() if digest in {"UNVERIFIED", "NOT_PRESENT"}
    ]
    if unresolved:
        raise ProvenanceError(f"snapshot hashes remain unverified: {sorted(unresolved)}")
    malformed = [
        name
        for name, digest in files.items()
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None
    ]
    if malformed:
        raise ProvenanceError(f"snapshot SHA-256 values are malformed: {sorted(malformed)}")
    if review.get("review_status") != "APPROVED" or review.get("approved") is not True:
        raise ProvenanceError("remote-code review is not approved")
    if review.get("trust_remote_code_allowed") is not True:
        raise ProvenanceError("trust_remote_code is not allowed")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or reviewer.strip() != reviewer:
        raise ProvenanceError("approved review must name a canonical reviewer")
    _validate_reviewed_at_utc(review.get("reviewed_at_utc"))
