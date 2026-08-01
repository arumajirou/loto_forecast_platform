from __future__ import annotations

import hashlib
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.data.lineage import sha256_file


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def save_pickle_model(payload: Any, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
    return target


def load_pickle_model(path: str | Path) -> Any:
    with Path(path).open("rb") as stream:
        return pickle.load(stream)


def artifact_summary(path: str | Path) -> dict[str, Any]:
    """Return deterministic size and SHA-256 evidence for a file or directory."""

    item = Path(path)

    if not item.exists():
        return {
            "exists": False,
            "artifact_type": "missing",
        }

    if item.is_file():
        return {
            "exists": True,
            "artifact_type": "file",
            "size_bytes": item.stat().st_size,
            "sha256": sha256_file(item),
            "file_count": 1,
        }

    if item.is_dir():
        files = sorted(
            candidate
            for candidate in item.rglob("*")
            if candidate.is_file()
        )

        digest = hashlib.sha256()
        total_size = 0
        entries: list[dict[str, Any]] = []

        for file_path in files:
            relative = file_path.relative_to(item).as_posix()
            file_sha256 = sha256_file(file_path)
            size_bytes = file_path.stat().st_size

            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(bytes.fromhex(file_sha256))

            total_size += size_bytes
            entries.append(
                {
                    "path": relative,
                    "size_bytes": size_bytes,
                    "sha256": file_sha256,
                }
            )

        return {
            "exists": True,
            "artifact_type": "directory",
            "size_bytes": total_size,
            "sha256": digest.hexdigest(),
            "file_count": len(entries),
            "files": entries,
        }

    return {
        "exists": True,
        "artifact_type": "unsupported",
    }


def model_manifest(
    path: str | Path,
    *,
    model_id: str,
    library: str,
    library_version: str | None,
    load_test_status: str,
    prediction_test_status: str,
) -> dict[str, Any]:
    item = Path(path)
    manifest: dict[str, Any] = {
        "path": str(item),
        "exists": item.exists(),
        "model_id": model_id,
        "library": library,
        "library_version": library_version,
        "created_at": utc_now_iso(),
        "load_test_status": load_test_status,
        "prediction_test_status": prediction_test_status,
    }
    manifest.update(artifact_summary(item))
    return manifest
