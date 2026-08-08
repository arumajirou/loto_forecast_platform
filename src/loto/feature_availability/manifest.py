"""Atomic deterministic Feature Availability manifest persistence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .contracts import FeatureManifest
from .validator import assert_feature_manifest_valid


class ManifestIntegrityError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestIntegrityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_manifest_bytes(manifest: FeatureManifest) -> bytes:
    payload = manifest.model_dump(mode="json", exclude_none=False)
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def manifest_sha256(manifest: FeatureManifest) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_feature_manifest(
    path: str | Path,
    manifest: FeatureManifest,
    *,
    allow_overwrite: bool = False,
) -> tuple[Path, Path]:
    target = Path(path)
    sidecar = target.with_name(f"{target.name}.sha256")
    if not allow_overwrite and (target.exists() or sidecar.exists()):
        raise FileExistsError("feature manifest evidence is immutable by default")
    assert_feature_manifest_valid(manifest)
    payload = canonical_manifest_bytes(manifest)
    digest = hashlib.sha256(payload).hexdigest()
    sidecar_payload = f"{digest}  {target.name}\n".encode()
    _atomic_write(target, payload)
    try:
        _atomic_write(sidecar, sidecar_payload)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target, sidecar


def read_feature_manifest(path: str | Path) -> FeatureManifest:
    target = Path(path)
    sidecar = target.with_name(f"{target.name}.sha256")
    if not target.is_file() or not sidecar.is_file():
        raise ManifestIntegrityError("manifest and SHA-256 sidecar are both required")
    payload = target.read_bytes()
    expected_line = sidecar.read_text(encoding="utf-8").strip()
    expected_parts = expected_line.split("  ", 1)
    if len(expected_parts) != 2 or expected_parts[1] != target.name:
        raise ManifestIntegrityError("invalid SHA-256 sidecar format or filename")
    actual = hashlib.sha256(payload).hexdigest()
    if expected_parts[0] != actual:
        raise ManifestIntegrityError("feature manifest SHA-256 mismatch")
    try:
        json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
        manifest = FeatureManifest.model_validate_json(payload)
    except ManifestIntegrityError:
        raise
    except Exception as exc:
        raise ManifestIntegrityError("feature manifest schema validation failed") from exc
    assert_feature_manifest_valid(manifest)
    return manifest


__all__ = [
    "ManifestIntegrityError",
    "canonical_manifest_bytes",
    "manifest_sha256",
    "read_feature_manifest",
    "write_feature_manifest",
]
