from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def write_sha256sums(root: Path, *, output_name: str = "SHA256SUMS") -> Path:
    output = root / output_name
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != output_name)
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in files]
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return output
