from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.adapters.timer_s1.contracts import CANONICAL_REPO, MIRROR_REPO, UNPINNED

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ArtifactRecord(ManifestModel):
    path: str
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = None
    required: bool = True
    kind: str

    @field_validator("sha256")
    @classmethod
    def validate_hash(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("artifact sha256 must be lowercase hexadecimal")
        return value


class TimerS1ModelManifest(ManifestModel):
    schema_version: int
    model_id: str
    canonical_repo: str
    mirror_repo: str
    arxiv_id: str
    license: str
    gated: bool
    trust_remote_code: bool
    model_revision: str
    source_revision: str
    observed_model_revision: str
    observed_source_revision: str
    mirror_revision: str
    package_versions: dict[str, str]
    python_compatibility: str
    artifacts: tuple[ArtifactRecord, ...]
    mirror_fallback_enabled: bool = False

    @field_validator(
        "model_revision",
        "source_revision",
        "observed_model_revision",
        "observed_source_revision",
        "mirror_revision",
    )
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if value != UNPINNED and not _REVISION.fullmatch(value):
            raise ValueError("revision must be UNPINNED or a lowercase 40-character SHA")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> TimerS1ModelManifest:
        if self.model_id != "timer-s1":
            raise ValueError("manifest model_id must be timer-s1")
        if self.canonical_repo != CANONICAL_REPO:
            raise ValueError("canonical repository mismatch")
        if self.mirror_repo != MIRROR_REPO:
            raise ValueError("mirror repository mismatch")
        if self.mirror_fallback_enabled:
            raise ValueError("mirror fallback is forbidden until complete byte parity is proven")
        paths = [item.path for item in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest artifact paths must be unique")
        return self

    @property
    def formal_pin_complete(self) -> bool:
        return (
            self.model_revision != UNPINNED
            and self.source_revision != UNPINNED
            and all(item.sha256 is not None for item in self.artifacts if item.required)
        )


def load_manifest(path: Path) -> TimerS1ModelManifest:
    return TimerS1ModelManifest.model_validate_json(path.read_text(encoding="utf-8"))


def canonical_manifest_sha256(manifest: TimerS1ModelManifest) -> str:
    import hashlib

    payload = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
