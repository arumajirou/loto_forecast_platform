from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value) + b"\n")


def write_artifact_manifest(directory: Path) -> tuple[Path, Path]:
    excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        if relative in excluded:
            continue
        entries.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest_path = directory / "ARTIFACT_MANIFEST.json"
    atomic_write_json(manifest_path, {"schema_version": "artifact-manifest-v1", "files": entries})

    checksum_lines = [
        f"{entry['sha256']}  {entry['path']}" for entry in entries
    ] + [f"{sha256_file(manifest_path)}  ARTIFACT_MANIFEST.json"]
    checksum_path = directory / "SHA256SUMS"
    atomic_write_bytes(checksum_path, ("\n".join(checksum_lines) + "\n").encode("utf-8"))
    return manifest_path, checksum_path


def verify_sha256s(directory: Path) -> bool:
    checksum_path = directory / "SHA256SUMS"
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", maxsplit=1)
        path = directory / relative
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True
