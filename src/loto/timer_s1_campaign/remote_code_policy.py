from __future__ import annotations

import hashlib
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RemoteCodeReview(ReviewModel):
    schema_version: int
    status: str
    source_revision: str
    reviewed_files: dict[str, str]
    shell_execution: bool
    subprocess_execution: bool
    dynamic_download: bool
    arbitrary_file_write: bool
    unapproved_external_imports: bool
    reviewer: str
    reviewed_at: str

    @field_validator("reviewed_files")
    @classmethod
    def validate_file_set(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != _ALLOWED_REMOTE_CODE:
            raise ValueError("remote-code review must cover the exact allowlist")
        return value

    @model_validator(mode="after")
    def validate_review(self) -> RemoteCodeReview:
        if self.status != "APPROVED":
            raise ValueError("remote-code review is not approved")
        if any(
            (
                self.shell_execution,
                self.subprocess_execution,
                self.dynamic_download,
                self.arbitrary_file_write,
                self.unapproved_external_imports,
            )
        ):
            raise ValueError("remote-code review contains a prohibited capability")
        if not self.reviewer.strip() or not self.reviewed_at.strip():
            raise ValueError("reviewer and reviewed_at are required")
        return self


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
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"snapshot contains symlink: {path.relative_to(root)}")
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        if root not in resolved.parents:
            raise ValueError("snapshot file escapes snapshot root")
        if path.suffix == ".py":
            python_files.add(path.relative_to(root).as_posix())
    if python_files != _ALLOWED_REMOTE_CODE:
        raise ValueError("snapshot remote Python files do not match allowlist")

    manifest_by_path = {item.path: item for item in manifest.artifacts}
    for relative_path, expected_hash in review.reviewed_files.items():
        path = root / relative_path
        if not path.is_file():
            raise ValueError(f"reviewed remote-code file is missing: {relative_path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(f"remote-code hash mismatch: {relative_path}")
        record = manifest_by_path.get(relative_path)
        if record is None or record.sha256 != actual_hash:
            raise ValueError(f"manifest does not bind remote code: {relative_path}")
