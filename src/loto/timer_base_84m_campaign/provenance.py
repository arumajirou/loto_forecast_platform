from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MODEL_ID = "timer-base-84m"
REPO_ID = "thuml/timer-base-84m"
MODEL_REVISION = "70077a71acce1b4c00d98332fcaabc694255d8e5"
WEIGHT_SHA256 = "9c3d18f12ffe1ea7d4fa70eb3304b26e3841164a6a265fbae4f7a05cd213aa3d"
SOURCE_REPOSITORY = "https://github.com/thuml/Large-Time-Series-Model"
SOURCE_REVISION = "1ff8d1afc073182e6d46022069ff32470ab47945"
TRANSFORMERS_VERSION = "4.40.1"
PYTHON_LANE = ">=3.10,<3.11"
LICENSE = "Apache-2.0"
EXPECTED_REMOTE_FILES = frozenset(
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


class ProvenanceError(ValueError):
    pass


def load_review(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_remote_code_review(review: dict[str, Any]) -> None:
    if review.get("model_revision") != MODEL_REVISION:
        raise ProvenanceError("remote-code review model revision mismatch")
    files = review.get("files")
    if not isinstance(files, dict) or frozenset(files) != EXPECTED_REMOTE_FILES:
        raise ProvenanceError("remote-code file allowlist mismatch")
    if files.get("model.safetensors") != WEIGHT_SHA256:
        raise ProvenanceError("model weight hash mismatch")
    unverified = [name for name, digest in files.items() if digest in {"UNVERIFIED", "NOT_PRESENT"}]
    if unverified:
        raise ProvenanceError(f"remote-code hashes remain unverified: {sorted(unverified)}")
    if review.get("review_status") != "APPROVED" or review.get("approved") is not True:
        raise ProvenanceError("remote-code review is not approved")
    if review.get("trust_remote_code_allowed") is not True:
        raise ProvenanceError("trust_remote_code is not allowed")
