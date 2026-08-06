from __future__ import annotations

import json
import re
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
EXPECTED_REMOTE_CODE_FILES = frozenset(
    {"configuration_timer.py", "modeling_timer.py", "ts_generation_mixin.py"}
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ProvenanceError(ValueError):
    pass


def load_review(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_remote_code_review(review: dict[str, Any]) -> None:
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

    files = review.get("files")
    if not isinstance(files, dict) or frozenset(files) != EXPECTED_SNAPSHOT_FILES:
        raise ProvenanceError("snapshot file allowlist mismatch")
    remote_code_files = review.get("remote_code_files")
    if not isinstance(remote_code_files, list):
        raise ProvenanceError("remote-code execution allowlist mismatch")
    if frozenset(remote_code_files) != EXPECTED_REMOTE_CODE_FILES:
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
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise ProvenanceError("approved review must name a reviewer")
    if not isinstance(review.get("reviewed_at_utc"), str) or not review["reviewed_at_utc"].strip():
        raise ProvenanceError("approved review must record reviewed_at_utc")
