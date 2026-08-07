from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def finalize_manifest(root: Path) -> dict[str, Any]:
    excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    files = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() not in excluded
    ]
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in files
    ]
    manifest = {"schema_version": 1, "file_count": len(entries), "files": entries}
    write_json(root / "ARTIFACT_MANIFEST.json", manifest)
    lines = [f"{entry['sha256']}  {entry['path']}" for entry in entries]
    suffix = "\n" if lines else ""
    (root / "SHA256SUMS").write_text("\n".join(lines) + suffix, encoding="utf-8")
    return manifest


def _seal_payload(run_id: str, predictions: list[list[float]]) -> bytes:
    payload = {"actual_known": False, "predictions": predictions, "run_id": run_id}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def seal_predictions(
    run_id: str,
    predictions: list[list[float]],
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = created_at or datetime.now(UTC)
    digest = hashlib.sha256(_seal_payload(run_id, predictions)).hexdigest()
    return {
        "schema_version": 1,
        "run_id": run_id,
        "actual_known": False,
        "created_at_utc": timestamp.astimezone(UTC).isoformat(),
        "prediction_sha256": digest,
    }


def verify_prediction_seal(seal: dict[str, Any], predictions: list[list[float]]) -> bool:
    expected = hashlib.sha256(_seal_payload(str(seal["run_id"]), predictions)).hexdigest()
    return bool(seal.get("actual_known") is False and seal.get("prediction_sha256") == expected)
