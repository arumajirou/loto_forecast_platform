from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from loto.toto2_campaign.model_manifest import (
    ARTIFACT_SHA256,
    ARTIFACT_SIZE_BYTES,
    MODEL_REVISION,
    REPO_ID,
)


@dataclass(frozen=True)
class ArtifactRecord:
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SnapshotEvidence:
    repo_id: str
    revision: str
    files: Mapping[str, ArtifactRecord]


def validate_snapshot_evidence(evidence: SnapshotEvidence) -> None:
    if evidence.repo_id != REPO_ID:
        raise ValueError("snapshot repo_id does not match the pinned model")
    if evidence.revision != MODEL_REVISION:
        raise ValueError("snapshot revision does not match the pinned model")
    if set(evidence.files) != set(ARTIFACT_SHA256):
        raise ValueError("snapshot file inventory differs from the pinned inventory")
    for name, expected_sha in ARTIFACT_SHA256.items():
        actual = evidence.files[name]
        if actual.sha256 != expected_sha:
            raise ValueError(f"snapshot SHA-256 mismatch: {name}")
        expected_size = ARTIFACT_SIZE_BYTES.get(name)
        if expected_size is not None and actual.size_bytes != expected_size:
            raise ValueError(f"snapshot size mismatch: {name}")
        if actual.size_bytes <= 0:
            raise ValueError(f"snapshot file is empty: {name}")


def require_safe_snapshot_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("snapshot_path must be absolute")
    if ".." in candidate.parts:
        raise ValueError("snapshot_path must not contain parent traversal")
    return candidate
