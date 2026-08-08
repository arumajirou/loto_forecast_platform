"""Durable manifest and verification for NeuralForecast search-space evidence."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .neuralforecast_search_space import SearchSpaceProfile, write_search_space_profile

PROFILE_NAME = "SEARCH_SPACE_PROFILE.json"
PROFILE_SUM_NAME = "SEARCH_SPACE_PROFILE.sha256"
MANIFEST_NAME = "SEARCH_SPACE_PROFILE_MANIFEST.json"
MANIFEST_SUM_NAME = "SEARCH_SPACE_PROFILE_MANIFEST.sha256"


class SearchSpaceArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    profile_schema_version: str
    profile_sha256: str
    profile_file_sha256: str
    context: dict[str, Any] = Field(default_factory=dict)
    files: tuple[dict[str, str], ...]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def persist_search_space_artifacts(
    directory: str | Path,
    profile: SearchSpaceProfile,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist profile, checksums and a dedicated artifact manifest atomically per file."""

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    profile_result = write_search_space_profile(root, profile)
    profile_path = root / PROFILE_NAME
    profile_sum_path = root / PROFILE_SUM_NAME
    profile_file_sha256 = _sha256_file(profile_path)
    manifest = SearchSpaceArtifactManifest(
        profile_schema_version=profile.schema_version,
        profile_sha256=profile.profile_sha256,
        profile_file_sha256=profile_file_sha256,
        context=dict(context or {}),
        files=(
            {"path": PROFILE_NAME, "sha256": profile_file_sha256},
            {"path": PROFILE_SUM_NAME, "sha256": _sha256_file(profile_sum_path)},
        ),
    )
    manifest_bytes = (
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    manifest_sha256 = _sha256_bytes(manifest_bytes)
    _atomic_write(root / MANIFEST_NAME, manifest_bytes)
    _atomic_write(
        root / MANIFEST_SUM_NAME,
        f"{manifest_sha256}  {MANIFEST_NAME}\n".encode(),
    )
    verified = verify_search_space_artifacts(root)
    if verified["status"] != "PASS":
        raise RuntimeError(f"search-space artifact verification failed: {verified}")
    return {
        **profile_result,
        "manifest_path": str(root / MANIFEST_NAME),
        "manifest_sha256_path": str(root / MANIFEST_SUM_NAME),
        "manifest_sha256": manifest_sha256,
        "verification_status": verified["status"],
    }


def _parse_checksum(path: Path, expected_name: str) -> str:
    fields = path.read_text(encoding="utf-8").strip().split()
    if len(fields) != 2 or fields[1] != expected_name:
        raise ValueError(f"invalid checksum record in {path.name}")
    return fields[0]


def verify_search_space_artifacts(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    required = [PROFILE_NAME, PROFILE_SUM_NAME, MANIFEST_NAME, MANIFEST_SUM_NAME]
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        return {"status": "FAIL", "missing": missing, "failed_checks": ["required_files"]}

    failed: list[str] = []
    try:
        profile_digest = _sha256_file(root / PROFILE_NAME)
        if _parse_checksum(root / PROFILE_SUM_NAME, PROFILE_NAME) != profile_digest:
            failed.append("profile_checksum")
        manifest_digest = _sha256_file(root / MANIFEST_NAME)
        if _parse_checksum(root / MANIFEST_SUM_NAME, MANIFEST_NAME) != manifest_digest:
            failed.append("manifest_checksum")
        profile = SearchSpaceProfile.model_validate_json(
            (root / PROFILE_NAME).read_text(encoding="utf-8")
        )
        manifest = SearchSpaceArtifactManifest.model_validate_json(
            (root / MANIFEST_NAME).read_text(encoding="utf-8")
        )
        if manifest.profile_sha256 != profile.profile_sha256:
            failed.append("profile_contract_sha256")
        if manifest.profile_file_sha256 != profile_digest:
            failed.append("manifest_profile_file_sha256")
        entries = {item["path"]: item["sha256"] for item in manifest.files}
        for name in (PROFILE_NAME, PROFILE_SUM_NAME):
            if entries.get(name) != _sha256_file(root / name):
                failed.append(f"manifest_entry:{name}")
    except Exception as exc:
        failed.append(f"exception:{type(exc).__name__}:{exc}")
    return {
        "status": "PASS" if not failed else "FAIL",
        "missing": missing,
        "failed_checks": failed,
    }
