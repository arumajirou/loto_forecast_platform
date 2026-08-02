from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of *path* without loading it into memory."""
    target = Path(path)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return value


class ManifestWriter:
    """Atomically write run manifests.

    Atomic replacement prevents a process interruption from leaving a partially
    written JSON file behind.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(self, manifest: Any) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            _to_jsonable(manifest),
            ensure_ascii=False,
            indent=2,
            default=_to_jsonable,
        )
        tmp = self.path.with_suffix(self.path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(self.path)
        return self.path
