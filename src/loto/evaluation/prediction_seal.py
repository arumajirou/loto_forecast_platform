"""Immutable prediction persistence and SHA-256 sealing."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SAFE_STEM = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True, slots=True)
class SealedPrediction:
    record_path: Path
    seal_path: Path
    record_sha256: str
    sealed_at_utc: str


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    """Sync parent-directory metadata where directory descriptors are supported."""

    if os.name == "nt":
        return

    descriptor = os.open(path, os.O_RDONLY)

    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")

    if temporary.exists():
        raise FileExistsError(f"temporary artifact already exists: {temporary}")

    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )

    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
        _fsync_directory(path.parent)

    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_json_once(
    path: Path,
    payload: Mapping[str, Any],
) -> str:
    """Write one immutable canonical JSON artifact and return its SHA."""

    _atomic_write_once(
        path,
        canonical_json_bytes(payload),
    )

    return sha256_file(path)


def seal_prediction_record(
    output_dir: Path,
    *,
    stem: str,
    record: Mapping[str, Any],
) -> SealedPrediction:
    """Persist a target-free prediction, then persist its SHA seal."""

    if _SAFE_STEM.fullmatch(stem) is None:
        raise ValueError(f"unsafe prediction artifact stem: {stem!r}")

    if record.get("target_actual_included") is not False:
        raise ValueError("prediction record must explicitly set target_actual_included=false")

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    record_path = output_dir / f"{stem}.prediction.json"

    record_sha = write_json_once(
        record_path,
        record,
    )

    sealed_at = utc_now()

    seal_path = output_dir / f"{stem}.prediction.seal.json"

    write_json_once(
        seal_path,
        {
            "schema_version": "oof-prediction-seal.v1",
            "prediction_record": record_path.name,
            "prediction_record_sha256": record_sha,
            "sealed_at_utc": sealed_at,
            "target_actual_read": False,
        },
    )

    sealed = SealedPrediction(
        record_path=record_path,
        seal_path=seal_path,
        record_sha256=record_sha,
        sealed_at_utc=sealed_at,
    )

    verify_sealed_prediction(sealed)

    return sealed


def verify_sealed_prediction(
    sealed: SealedPrediction,
) -> None:
    """Reject a missing, mismatched, or mutated prediction seal."""

    if not sealed.record_path.is_file():
        raise FileNotFoundError(sealed.record_path)

    if not sealed.seal_path.is_file():
        raise FileNotFoundError(sealed.seal_path)

    seal = json.loads(sealed.seal_path.read_text(encoding="utf-8"))

    if seal["prediction_record"] != sealed.record_path.name:
        raise ValueError("seal prediction path mismatch")

    actual_sha = sha256_file(sealed.record_path)

    expected_sha = seal["prediction_record_sha256"]

    if actual_sha != expected_sha:
        raise ValueError("prediction record SHA-256 mismatch")

    if actual_sha != sealed.record_sha256:
        raise ValueError("sealed prediction object SHA mismatch")

    if seal["target_actual_read"] is not False:
        raise ValueError("prediction seal is not pre-actual")
