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
    if item.exists() and item.is_file():
        manifest.update({
            "size_bytes": item.stat().st_size,
            "sha256": sha256_file(item),
        })
    elif item.exists() and item.is_dir():
        files = sorted(path for path in item.rglob("*") if path.is_file())
        digest = hashlib.sha256()
        total = 0
        entries = []
        for file_path in files:
            rel = file_path.relative_to(item).as_posix()
            file_sha = sha256_file(file_path)
            size = file_path.stat().st_size
            total += size
            digest.update(rel.encode("utf-8"))
            digest.update(file_sha.encode("utf-8"))
            entries.append({"path": rel, "size_bytes": size, "sha256": file_sha})
        manifest.update({
            "size_bytes": total,
            "sha256": digest.hexdigest(),
            "files": entries,
        })
    return manifest
