"""Filesystem, JSON, checksum, and array-evidence integrity helpers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .constants import CertificationError


def sha_file(path: Path) -> str:
    require_regular_file(path, path.name)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def compact_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def require_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise CertificationError(f"{label} must not be a symbolic link: {path}")
    if not path.is_file():
        raise CertificationError(f"{label} is not a regular file: {path}")
    return path


def require_directory(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise CertificationError(f"{label} must not be a symbolic link: {path}")
    if not path.is_dir():
        raise CertificationError(f"{label} is not a directory: {path}")
    return path


def load_json(path: Path) -> dict[str, Any]:
    require_regular_file(path, "JSON artifact")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CertificationError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CertificationError(f"JSON root must be an object: {path}")
    return payload


def safe_name(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or ".." in path.parts:
        raise CertificationError(f"unsafe artifact path: {value!r}")
    if not value or path.name != value or "\\" in value:
        raise CertificationError(f"invalid artifact name: {value!r}")
    return value


def checksums(path: Path, expected: set[str]) -> dict[str, str]:
    require_regular_file(path, "checksum file")
    result: dict[str, str] = {}
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CertificationError(f"cannot read checksum file: {exc}") from exc
    for row in rows:
        if not row.strip():
            continue
        try:
            digest, name = row.split("  ", 1)
        except ValueError as exc:
            raise CertificationError(f"invalid checksum row: {row!r}") from exc
        name = safe_name(name)
        if not valid_sha256(digest):
            raise CertificationError(f"invalid SHA-256: {name}")
        if name in result:
            raise CertificationError(f"duplicate checksum entry: {name}")
        result[name] = digest
    if set(result) != expected:
        raise CertificationError(
            f"checksum coverage mismatch: expected={sorted(expected)} actual={sorted(result)}"
        )
    return result


def inside(path: Path, root: Path, label: str) -> Path:
    root_resolved = root.resolve()
    lexical = Path(os.path.abspath(path))
    try:
        relative = lexical.relative_to(root_resolved)
    except ValueError as exc:
        raise CertificationError(f"{label} escapes expected root: {lexical}") from exc
    current = root_resolved
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise CertificationError(f"{label} contains a symbolic-link path component: {current}")
    resolved = lexical.resolve()
    if resolved != lexical:
        raise CertificationError(f"{label} is not a direct path: {lexical}")
    return resolved


def resolve_requested_root(repo_root: Path, requested: Path, label: str) -> Path:
    candidate = repo_root / requested if not requested.is_absolute() else requested
    lexical = Path(os.path.abspath(candidate))
    if lexical.is_symlink():
        raise CertificationError(f"{label} must not be a symbolic link: {lexical}")
    return lexical.resolve()


def valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def verify_array_evidence(
    evidence: object,
    *,
    expected_shape: list[int],
    label: str,
) -> None:
    if not isinstance(evidence, dict):
        raise CertificationError(f"{label} evidence must be an object")
    if evidence.get("shape") != expected_shape:
        raise CertificationError(f"{label} shape evidence mismatch")
    if evidence.get("dtype") != "float64-le" or evidence.get("finite") is not True:
        raise CertificationError(f"{label} dtype/finite evidence mismatch")
    if not valid_sha256(evidence.get("sha256")):
        raise CertificationError(f"{label} SHA-256 evidence is invalid")
    for field in ("minimum", "maximum"):
        if field in evidence and not finite_number(evidence[field]):
            raise CertificationError(f"{label} {field} evidence is non-finite")
