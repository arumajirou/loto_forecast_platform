from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.adapters.timer_s1.contracts import CANONICAL_REPO, MIRROR_REPO, UNPINNED

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_ARTIFACT_KINDS = {
    "config.json": "config",
    "model.safetensors.index.json": "weight-index",
    "model-00001-of-00004.safetensors": "weight",
    "model-00002-of-00004.safetensors": "weight",
    "model-00003-of-00004.safetensors": "weight",
    "model-00004-of-00004.safetensors": "weight",
    "configuration_TimerS1.py": "remote-code",
    "modeling_TimerS1.py": "remote-code",
    "ts_generation_mixin.py": "remote-code",
}


class ManifestModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )


class ArtifactRecord(ManifestModel):
    path: str
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = None
    required: bool = True
    kind: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value or "\\" in value or "\x00" in value:
            raise ValueError("artifact path must be a non-empty POSIX relative path")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("artifact path must remain inside the snapshot root")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_hash(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("artifact sha256 must be lowercase hexadecimal")
        return value

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("artifact kind must be non-empty")
        return value


class TimerS1ModelManifest(ManifestModel):
    schema_version: Literal[1]
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
        if self.license != "Apache-2.0":
            raise ValueError("manifest license must be Apache-2.0")
        if self.gated:
            raise ValueError("Timer-S1 canonical repository is not declared gated")
        if not self.trust_remote_code:
            raise ValueError("Timer-S1 manifest must record the upstream remote-code boundary")
        if self.mirror_fallback_enabled:
            raise ValueError("mirror fallback is forbidden until complete byte parity is proven")
        paths = [item.path for item in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest artifact paths must be unique")
        artifacts_by_path = {item.path: item for item in self.artifacts}
        missing = sorted(set(_REQUIRED_ARTIFACT_KINDS) - set(artifacts_by_path))
        if missing:
            raise ValueError(f"manifest is missing required artifacts: {', '.join(missing)}")
        for path, expected_kind in _REQUIRED_ARTIFACT_KINDS.items():
            record = artifacts_by_path[path]
            if not record.required:
                raise ValueError(f"required Timer-S1 artifact marked optional: {path}")
            if record.kind != expected_kind:
                raise ValueError(
                    f"Timer-S1 artifact kind mismatch for {path}: expected {expected_kind}"
                )
        return self

    def artifact(self, path: str) -> ArtifactRecord:
        for item in self.artifacts:
            if item.path == path:
                return item
        raise ValueError(f"manifest is missing required artifact: {path}")

    def artifact_sha256(self, path: str) -> str:
        record = self.artifact(path)
        if record.sha256 is None:
            raise ValueError(f"manifest artifact hash is unpinned: {path}")
        return record.sha256

    @property
    def weight_set_sha256(self) -> str | None:
        weights = sorted(
            (item for item in self.artifacts if item.required and item.kind == "weight"),
            key=lambda item: item.path,
        )
        if not weights:
            return None
        if any(item.sha256 is None or item.size_bytes is None for item in weights):
            return None
        payload = {
            "schema": "timer-s1-weight-set-v1",
            "artifacts": [
                {
                    "path": item.path,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                }
                for item in weights
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def formal_pin_complete(self) -> bool:
        required_complete = all(
            item.sha256 is not None and item.size_bytes is not None
            for item in self.artifacts
            if item.required
        )
        return (
            self.model_revision != UNPINNED
            and self.source_revision != UNPINNED
            and required_complete
            and self.weight_set_sha256 is not None
        )


def load_manifest(path: Path) -> TimerS1ModelManifest:
    return TimerS1ModelManifest.model_validate_json(path.read_text(encoding="utf-8"))


def canonical_manifest_sha256(manifest: TimerS1ModelManifest) -> str:
    payload = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
