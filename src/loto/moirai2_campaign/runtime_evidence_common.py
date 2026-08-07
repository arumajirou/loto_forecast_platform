from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any



FORMAL_CASE_NAMES = (
    "draw-target-only",
    "draw-past-only",
    "draw-past-known-future",
    "calendar-target-only",
    "calendar-past-only",
    "calendar-past-known-future",
)
EXPECTED_QUANTILE_KEYS = tuple(f"q{value / 10:.1f}" for value in range(1, 10))
EXPECTED_SAVE_LOAD_STATUS = "BASE_SNAPSHOT_RELOADED"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_OBJECT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


class RuntimeEvidenceGateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManifestVerification:
    manifest_entry_count: int
    artifact_manifest_file_count: int
    actual_file_count: int
    verified_file_count: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class CaseVerification:
    case_name: str
    runtime_lane: str
    requested_device: str
    process_a: int
    process_b: int
    prediction_sha256: str
    model_revision: str
    config_sha256: str
    weight_sha256: str
    quantile_keys: tuple[str, ...]
    external_gpu_verified: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["quantile_keys"] = list(self.quantile_keys)
        return payload


@dataclass(frozen=True)
class CampaignVerification:
    campaign_dir: str
    campaign_id: str
    runtime_lane: str
    requested_device: str
    source_commit: str
    source_tree: str
    lock_sha256: str
    snapshot_config_sha256: str
    snapshot_weight_sha256: str
    manifest: ManifestVerification
    cases: tuple[CaseVerification, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["manifest"] = self.manifest.as_dict()
        payload["cases"] = [case.as_dict() for case in self.cases]
        return payload


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeEvidenceGateError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeEvidenceGateError(f"JSON object is required: {path}")
    return payload


def _required_file(root: Path, relative_path: str) -> Path:
    path = root / relative_path
    if not path.is_file():
        raise RuntimeEvidenceGateError(
            f"required campaign artifact is missing: {relative_path}"
        )
    return path


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value in {"", "."}:
        raise RuntimeEvidenceGateError(f"unsafe manifest path: {value!r}")
    normalized = path.as_posix()
    if normalized != value:
        raise RuntimeEvidenceGateError(f"non-canonical manifest path: {value!r}")
    return normalized


