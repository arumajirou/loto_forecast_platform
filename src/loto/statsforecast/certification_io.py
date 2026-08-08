from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return list(value)
    if hasattr(value, "value"):
        return value.value
    return repr(value)


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def write_json(path: Path, payload: Any) -> None:
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=json_default,
        ).encode("utf-8")
        + b"\n"
    )
    atomic_write(path, content)


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    columns = sorted({key for row in materialized for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in materialized:
            writer.writerow({key: row.get(key, "") for key in columns})
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest_and_sums(run_dir: Path) -> None:
    artifacts = []
    excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name not in excluded:
            artifacts.append(
                {
                    "path": path.relative_to(run_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    write_json(
        run_dir / "ARTIFACT_MANIFEST.json",
        {
            "schema_version": 1,
            "created_at_utc": utc_now(),
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        },
    )
    rows = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            rows.append(f"{sha256_file(path)}  {path.relative_to(run_dir).as_posix()}")
    atomic_write(run_dir / "SHA256SUMS", ("\n".join(rows) + "\n").encode("utf-8"))
