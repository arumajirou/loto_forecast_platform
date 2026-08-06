from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from loto.timer_s1_campaign.model_manifest import TimerS1ModelManifest

_REQUIRED_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}
_ALLOWED_REMOTE_CODE = {
    "configuration_TimerS1.py",
    "modeling_TimerS1.py",
    "ts_generation_mixin.py",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")


class ReviewModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )


class RemoteCodeReview(ReviewModel):
    schema_version: Literal[1]
    status: Literal["APPROVED"]
    source_revision: str
    reviewed_files: dict[str, str]
    shell_execution: Literal[False]
    subprocess_execution: Literal[False]
    dynamic_download: Literal[False]
    arbitrary_file_write: Literal[False]
    unapproved_external_imports: Literal[False]
    reviewer: str
    reviewed_at: datetime

    @field_validator("source_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if not _REVISION.fullmatch(value):
            raise ValueError("review source_revision must be a lowercase 40-character SHA")
        return value

    @field_validator("reviewed_files")
    @classmethod
    def validate_file_set(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != _ALLOWED_REMOTE_CODE:
            raise ValueError("remote-code review must cover the exact allowlist")
        if any(not _SHA256.fullmatch(digest) for digest in value.values()):
            raise ValueError("reviewed remote-code hashes must be lowercase SHA-256")
        return value

    @field_validator("reviewed_at", mode="before")
    @classmethod
    def parse_reviewed_at(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ValueError("reviewed_at must be an ISO-8601 datetime")

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reviewed_at must include a timezone")
        return value

    @field_validator("reviewer")
    @classmethod
    def validate_reviewer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reviewer is required")
        return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_snapshot(
    snapshot_path: Path,
    manifest: TimerS1ModelManifest,
    review: RemoteCodeReview,
) -> None:
    if not snapshot_path.is_absolute():
        raise ValueError("snapshot path must be absolute")
    if not snapshot_path.is_dir() or snapshot_path.is_symlink():
        raise ValueError("snapshot path must be a real directory")
    if review.source_revision != manifest.source_revision:
        raise ValueError("remote-code review source revision mismatch")
    for key, expected in _REQUIRED_OFFLINE_ENV.items():
        if os.environ.get(key) != expected:
            raise ValueError(f"offline environment requirement not met: {key}")

    root = snapshot_path.resolve(strict=True)
    python_files: set[str] = set()
    snapshot_files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"snapshot contains symlink: {path.relative_to(root)}")
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        if root not in resolved.parents:
            raise ValueError("snapshot file escapes snapshot root")
        relative_path = path.relative_to(root).as_posix()
        snapshot_files.add(relative_path)
        if path.suffix == ".py":
            python_files.add(relative_path)
    if python_files != _ALLOWED_REMOTE_CODE:
        raise ValueError("snapshot remote Python files do not match allowlist")

    manifest_by_path = {item.path: item for item in manifest.artifacts}
    if snapshot_files != set(manifest_by_path):
        raise ValueError("snapshot file inventory does not exactly match the manifest")
    actual_hashes: dict[str, str] = {}
    for relative_path, record in manifest_by_path.items():
        path = root / relative_path
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"manifest artifact is not a regular file: {relative_path}")
        if record.size_bytes is None or path.stat().st_size != record.size_bytes:
            raise ValueError(f"manifest artifact size mismatch: {relative_path}")
        if record.sha256 is None:
            raise ValueError(f"manifest artifact hash is unpinned: {relative_path}")
        actual_hash = sha256_file(path)
        if actual_hash != record.sha256:
            raise ValueError(f"manifest artifact hash mismatch: {relative_path}")
        actual_hashes[relative_path] = actual_hash

    for relative_path, expected_hash in review.reviewed_files.items():
        if actual_hashes.get(relative_path) != expected_hash:
            raise ValueError(f"remote-code review hash mismatch: {relative_path}")
