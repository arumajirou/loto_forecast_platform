from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

MANIFEST_NAME = "P7D_BUNDLE_MANIFEST.json"
CHECKSUM_NAME = "P7D_SHA256SUMS"
COMPLETE_NAME = "P7D_BUNDLE_COMPLETE"
METADATA_NAMES = {MANIFEST_NAME, CHECKSUM_NAME, COMPLETE_NAME}
MAX_ARCHIVE_MEMBERS = 200_000
MAX_MEMBER_UNCOMPRESSED_BYTES = 1024**4
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024**4
MAX_COMPRESSION_RATIO = 100_000
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_CHECKSUM_BYTES = 128 * 1024 * 1024


class P7DBundleError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_stream(handle: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except Exception as exc:
        raise P7DBundleError(f"failed to read JSON {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise P7DBundleError(f"JSON root must be an object: {path}")
    return payload


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise P7DBundleError(f"unsafe relative path: {value}")
    return path


def _checksum_entries(root: Path, checksum_name: str) -> dict[Path, str]:
    checksum_path = root / checksum_name
    if not checksum_path.is_file():
        raise P7DBundleError(f"missing checksum file: {checksum_path}")
    entries: dict[Path, str] = {}
    for line_number, line in enumerate(
        checksum_path.read_text("utf-8").splitlines(),
        1,
    ):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise P7DBundleError(f"invalid checksum line {line_number}: {checksum_name}")
        digest, token = parts
        relative = _safe_relative(token.strip().lstrip("*"))
        path = (root / Path(*relative.parts)).resolve()
        root_resolved = root.resolve()
        if root_resolved not in path.parents:
            raise P7DBundleError(f"checksum path escapes root: {token}")
        if path in entries:
            raise P7DBundleError(f"duplicate checksum path: {token}")
        entries[path] = digest.lower()
    if not entries:
        raise P7DBundleError(f"empty checksum inventory: {checksum_name}")
    return entries


def verify_checksum_inventory(
    root: Path,
    checksum_name: str,
    *,
    excluded_names: set[str] | None = None,
) -> str:
    entries = _checksum_entries(root, checksum_name)
    excluded = {checksum_name, *(excluded_names or set())}
    observed = {
        path.resolve() for path in root.rglob("*") if path.is_file() and path.name not in excluded
    }
    if set(entries) != observed:
        missing = sorted(str(path.relative_to(root)) for path in observed - set(entries))
        stale = sorted(str(path.relative_to(root)) for path in set(entries) - observed)
        raise P7DBundleError(
            f"checksum inventory mismatch for {checksum_name}: missing={missing}, stale={stale}"
        )
    for path, expected in entries.items():
        if not path.is_file() or sha256_file(path) != expected:
            raise P7DBundleError(f"checksum mismatch: {path.relative_to(root)}")
    return sha256_file(root / checksum_name)


def _marker_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text("utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    if not values.get("RUN_ID") or not values.get("COMMIT_SHA"):
        raise P7DBundleError(f"incomplete marker: {path}")
    return values


def _read_return_code(path: Path) -> int:
    try:
        return int(path.read_text("utf-8").strip())
    except Exception as exc:
        raise P7DBundleError(f"invalid return-code file: {path}") from exc
