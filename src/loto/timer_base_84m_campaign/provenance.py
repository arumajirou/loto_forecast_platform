from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

MODEL_ID = "timer-base-84m"
REPO_ID = "thuml/timer-base-84m"
MODEL_REVISION = "70077a71acce1b4c00d98332fcaabc694255d8e5"
CONFIG_SHA256 = "8cf274b6192f6114a0988d1e70277c69531db3611866ae7d4c6f82819c469c7e"
WEIGHT_SHA256 = "9c3d18f12ffe1ea7d4fa70eb3304b26e3841164a6a265fbae4f7a05cd213aa3d"
SNAPSHOT_MANIFEST_SHA256 = "0cc9cd7d341e7a103f7c6bc4e3067af97dd4940576719d1bdd7ebcf3b3c54c2a"
REVIEW_PACKET_SHA256 = "0d7800ae8b70274b034cc5a37893ae806b21f0bee8da5854a470ffe257491512"
SOURCE_REPOSITORY = "https://github.com/thuml/Large-Time-Series-Model"
SOURCE_REVISION = "UNPINNED"
OBSERVED_SOURCE_HEAD = "1ff8d1afc073182e6d46022069ff32470ab47945"
TRANSFORMERS_VERSION = "4.40.1"
PYTHON_LANE = ">=3.10,<3.11"
LICENSE = "Apache-2.0"
SNAPSHOT_FILE_SHA256S = {
    ".gitattributes": "11ad7efa24975ee4b0c3c3a38ed18737f0658a5f75a0a96787b576a78a023361",
    "README.md": "da6dcfdebb53e79e97e159ca605942b7c8c580d4c816c60016349d5c5b0ed9bb",
    "config.json": CONFIG_SHA256,
    "configuration_timer.py": "bec2d7ed868b57d7046f097cad166d8e935920aa082cc6e9bb2cc53b9b626173",
    "generation_config.json": "f6f95f062b96cc8c5d0954c6540beff706aa6d0982b5474925c6639bc3b5def9",
    "model.safetensors": WEIGHT_SHA256,
    "modeling_timer.py": "a625da46370e044609f1cd601eb2899aaf8a8e2dd5966bcfadc9d7f89a5092ad",
    "ts_generation_mixin.py": "357d4aa6fd24f107bef5665f82fe2c7df278f4ff151c4493dbaa9f43655b55a1",
}
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
        "automated_static_scan",
        "execution_boundary",
        "review_artifact",
        "snapshot_audit",
        "snapshot_manifest_sha256",
    }
)
EXPECTED_EXECUTION_BOUNDARY_FIELDS = frozenset(
    {
        "checkpoint_load_executed",
        "cpu_inference_executed",
        "cuda_inference_executed",
        "model_import_executed",
        "trust_remote_code_executed",
    }
)
EXPECTED_SNAPSHOT_AUDIT_FIELDS = frozenset(
    {
        "artifact",
        "artifact_digest",
        "hash_report_job",
        "hash_report_run",
        "job",
        "workflow_run",
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
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        reviewed_at = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ProvenanceError("reviewed_at_utc must be valid ISO-8601") from exc
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() != timedelta(0):
        raise ProvenanceError("reviewed_at_utc must be timezone-aware UTC")


def _validate_automated_static_scan(value: Any) -> None:
    if not isinstance(value, dict):
        raise ProvenanceError("automated_static_scan must be an object")
    expected_fields = frozenset({"decision", "flagged_call_count", *EXPECTED_REMOTE_CODE_FILES})
    if frozenset(value) != expected_fields:
        raise ProvenanceError("automated_static_scan fields mismatch")
    if value.get("decision") != "SUPPORTING_EVIDENCE_ONLY_NO_HUMAN_APPROVAL":
        raise ProvenanceError("automated_static_scan decision mismatch")
    if value.get("flagged_call_count") != 0:
        raise ProvenanceError("automated_static_scan must retain zero flagged calls")
    for name in EXPECTED_REMOTE_CODE_FILES:
        record = value.get(name)
        if not isinstance(record, dict) or frozenset(record) != {"flagged_calls", "imports"}:
            raise ProvenanceError(f"automated_static_scan record malformed for {name}")
        if record.get("flagged_calls") != []:
            raise ProvenanceError(f"automated_static_scan flagged calls changed for {name}")
        imports = record.get("imports")
        if (
            not isinstance(imports, list)
            or not imports
            or any(not isinstance(item, str) or not item.strip() for item in imports)
        ):
            raise ProvenanceError(f"automated_static_scan imports malformed for {name}")


def _validate_execution_boundary(value: Any) -> None:
    if not isinstance(value, dict) or frozenset(value) != EXPECTED_EXECUTION_BOUNDARY_FIELDS:
        raise ProvenanceError("execution_boundary fields mismatch")
    if any(value[field] is not False for field in EXPECTED_EXECUTION_BOUNDARY_FIELDS):
        raise ProvenanceError("approval record must preserve the pre-execution boundary")


def _validate_review_artifact(value: Any) -> None:
    expected = {
        "kind": "timer-b2-human-review-packet",
        "sha256": REVIEW_PACKET_SHA256,
    }
    if value != expected:
        raise ProvenanceError("human review artifact identity mismatch")


def _validate_snapshot_audit(value: Any) -> None:
    if not isinstance(value, dict) or frozenset(value) != EXPECTED_SNAPSHOT_AUDIT_FIELDS:
        raise ProvenanceError("snapshot_audit fields mismatch")
    integer_fields = EXPECTED_SNAPSHOT_AUDIT_FIELDS - {"artifact_digest"}
    if any(not isinstance(value[field], int) or value[field] <= 0 for field in integer_fields):
        raise ProvenanceError("snapshot_audit numeric identifiers must be positive integers")
    artifact_digest = value.get("artifact_digest")
    if (
        not isinstance(artifact_digest, str)
        or not artifact_digest.startswith("sha256:")
        or _SHA256_PATTERN.fullmatch(artifact_digest.removeprefix("sha256:")) is None
    ):
        raise ProvenanceError("snapshot_audit artifact digest is malformed")


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
        "snapshot_manifest_sha256": SNAPSHOT_MANIFEST_SHA256,
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
    expected_files = {
        name: digest for name, digest in SNAPSHOT_FILE_SHA256S.items() if name != ".gitattributes"
    }
    if files != expected_files or frozenset(files) != EXPECTED_SNAPSHOT_FILES:
        raise ProvenanceError("snapshot file hashes do not match the reviewed allowlist")
    remote_code_files = review.get("remote_code_files")
    if remote_code_files != list(EXPECTED_REMOTE_CODE_FILES):
        raise ProvenanceError("remote-code execution allowlist mismatch")

    _validate_automated_static_scan(review.get("automated_static_scan"))
    _validate_execution_boundary(review.get("execution_boundary"))
    _validate_review_artifact(review.get("review_artifact"))
    _validate_snapshot_audit(review.get("snapshot_audit"))

    if review.get("review_status") != "HUMAN_REVIEW_APPROVED" or review.get("approved") is not True:
        raise ProvenanceError("remote-code review is not human-approved")
    if review.get("trust_remote_code_allowed") is not True:
        raise ProvenanceError("trust_remote_code is not allowed")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or reviewer.strip() != reviewer:
        raise ProvenanceError("approved review must name a canonical reviewer")
    _validate_reviewed_at_utc(review.get("reviewed_at_utc"))
