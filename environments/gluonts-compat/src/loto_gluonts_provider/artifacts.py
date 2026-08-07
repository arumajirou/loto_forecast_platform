from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize a JSON payload deterministically for hashing and persistence."""

    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def atomic_write_json(path: Path, payload: Any) -> str:
    """Persist canonical JSON with fsync and atomic rename, returning SHA-256."""

    path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json_bytes(payload)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return hashlib.sha256(content).hexdigest()
