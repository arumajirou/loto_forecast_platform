"""Provider-neutral request, package, model, and snapshot identity verification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import ArtifactIdentity, PackageIdentity, RequestIdentity, SnapshotIdentity


class IdentityVerificationError(RuntimeError):
    pass


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_request_identity(payload: Any, identity: RequestIdentity) -> str:
    actual = sha256_bytes(canonical_json_bytes(payload))
    if actual != identity.request_sha256:
        raise IdentityVerificationError("request SHA-256 mismatch")
    return actual


def verify_package_identity(
    identity: PackageIdentity,
    *,
    artifact_path: Path | None = None,
    version_reader: Callable[[str], str] = importlib.metadata.version,
) -> str:
    try:
        installed_version = version_reader(identity.distribution)
    except importlib.metadata.PackageNotFoundError as exc:
        raise IdentityVerificationError(
            f"required distribution is missing: {identity.distribution}"
        ) from exc
    if installed_version != identity.version:
        raise IdentityVerificationError(
            f"package version mismatch: expected {identity.version}, got {installed_version}"
        )
    if identity.artifact_sha256 is not None:
        if artifact_path is None:
            raise IdentityVerificationError(
                "package artifact path is required when artifact_sha256 is declared"
            )
        raw_artifact = artifact_path.expanduser()
        if raw_artifact.is_symlink():
            raise IdentityVerificationError("package artifact must not be a symlink")
        artifact = raw_artifact.resolve(strict=True)
        if not artifact.is_file() or sha256_file(artifact) != identity.artifact_sha256:
            raise IdentityVerificationError("package artifact SHA-256 mismatch")
    return installed_version


def _reject_symlink_components(root: Path, candidate: Path) -> None:
    relative = candidate.relative_to(root)
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise IdentityVerificationError(f"symlink is forbidden: {relative.as_posix()}")


def _reject_path_symlinks(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        if current.exists() and current.is_symlink():
            raise IdentityVerificationError(f"snapshot path contains a symlink: {current}")


def verify_file_identity(root: Path, identity: ArtifactIdentity) -> Path:
    root = root.expanduser().resolve(strict=True)
    candidate = root / identity.relative_path
    try:
        candidate.relative_to(root)
        _reject_symlink_components(root, candidate)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise IdentityVerificationError(
            f"artifact escapes or is missing from snapshot root: {identity.relative_path}"
        ) from exc
    if not resolved.is_file():
        raise IdentityVerificationError(f"artifact is not a regular file: {identity.relative_path}")
    if resolved.stat().st_size != identity.size_bytes:
        raise IdentityVerificationError(f"artifact size mismatch: {identity.relative_path}")
    actual_sha256 = sha256_file(resolved)
    if actual_sha256 != identity.sha256:
        raise IdentityVerificationError(f"artifact SHA-256 mismatch: {identity.relative_path}")
    return resolved


def verify_snapshot_identity(identity: SnapshotIdentity) -> dict[str, str]:
    raw_root = Path(identity.snapshot_root).expanduser()
    _reject_path_symlinks(raw_root)
    root = raw_root.resolve(strict=True)
    if not root.is_dir():
        raise IdentityVerificationError("snapshot_root is not a directory")
    if root.name != identity.expected_revision:
        raise IdentityVerificationError(
            f"snapshot revision mismatch: expected {identity.expected_revision}, got {root.name}"
        )
    verified: dict[str, str] = {}
    for artifact in identity.artifacts:
        path = verify_file_identity(root, artifact)
        verified[artifact.relative_path] = str(path)
    return verified
