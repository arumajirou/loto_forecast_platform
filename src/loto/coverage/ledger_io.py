from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from loto.coverage.ledger_types import (
    CoverageLedgerBlocked,
    CoverageLedgerPreflightError,
)


def absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def reject_symlink_components(path: Path, *, label: str) -> None:
    resolved = absolute(path)
    for candidate in (resolved, *resolved.parents):
        if candidate.exists() and candidate.is_symlink():
            raise CoverageLedgerPreflightError(
                f"{label} must not contain a symlink component: {candidate}"
            )


def require_regular_file(path: Path, *, label: str) -> None:
    reject_symlink_components(path, label=label)
    if not path.is_file():
        raise CoverageLedgerPreflightError(f"{label} is not a regular file: {path}")


def require_empty_output(path: Path) -> None:
    reject_symlink_components(path, label="output")
    if path.exists() and not path.is_dir():
        raise CoverageLedgerPreflightError(f"output is not a directory: {path}")
    if path.exists() and any(path.iterdir()):
        raise CoverageLedgerPreflightError(
            "instrumented coverage requires a new empty output directory"
        )
    path.mkdir(parents=True, exist_ok=True)


def git_blob_sha(path: Path) -> str:
    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()  # noqa: S324


def atomic_write_json(path: Path, payload: Any) -> None:
    reject_symlink_components(path.parent, label="artifact directory")
    if path.is_symlink():
        raise CoverageLedgerBlocked(f"artifact path is a symlink: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
