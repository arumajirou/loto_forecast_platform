from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CHRONOS_PACKAGE_VERSION = "2.3.1"
CHRONOS_PACKAGE_SOURCE_REVISION = "7dc4435706a4454feb79df44ca9f33631f3027bf"
CHRONOS_MODEL_REVISION = "29ec3766d36d6f73f0696f85560a422f50e8498c"
PYPI_WHEEL_SHA256 = "d9d00ec9b1621235bfb26685638bf054885f4c000863678f1c775dfab2697496"
PYPI_SDIST_SHA256 = "785116f3f10aaac44a315700c5e4de71a5fe6385c9c771722d688f402fe75083"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SnapshotFile(FrozenModel):
    path: str
    resolved_path: str
    size_bytes: int = Field(ge=0)
    sha256: str


class Chronos2ModelManifest(FrozenModel):
    schema_version: Literal[1] = 1
    status: Literal["VERIFIED", "REFERENCE_ONLY"]
    lane: Literal["legacy_reproduction", "current_reviewed"]
    package_name: Literal["chronos-forecasting"] = "chronos-forecasting"
    package_version: Literal["2.3.1"] = CHRONOS_PACKAGE_VERSION
    package_source_revision: str = CHRONOS_PACKAGE_SOURCE_REVISION
    pypi_wheel_sha256: str = PYPI_WHEEL_SHA256
    pypi_sdist_sha256: str = PYPI_SDIST_SHA256
    repo_id: Literal["amazon/chronos-2"] = "amazon/chronos-2"
    revision: str = CHRONOS_MODEL_REVISION
    snapshot_path: str
    files: tuple[SnapshotFile, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_model_manifest(
    snapshot_path: str | Path,
    *,
    lane: Literal["legacy_reproduction", "current_reviewed"],
    revision: str = CHRONOS_MODEL_REVISION,
) -> Chronos2ModelManifest:
    snapshot = Path(snapshot_path).expanduser().resolve()
    if not snapshot.is_dir():
        raise FileNotFoundError(f"snapshot directory does not exist: {snapshot}")
    if revision != CHRONOS_MODEL_REVISION:
        raise ValueError("the first provider increment permits only the reviewed model revision")
    required = [snapshot / "config.json", snapshot / "model.safetensors"]
    for path in required:
        if not path.exists() or not path.resolve().is_file():
            raise FileNotFoundError(f"required snapshot file is missing: {path}")

    entries: list[SnapshotFile] = []
    for path in sorted(item for item in snapshot.rglob("*") if item.is_file()):
        resolved = path.resolve()
        entries.append(
            SnapshotFile(
                path=path.relative_to(snapshot).as_posix(),
                resolved_path=str(resolved),
                size_bytes=resolved.stat().st_size,
                sha256=sha256_file(resolved),
            )
        )
    return Chronos2ModelManifest(
        status="VERIFIED",
        lane=lane,
        revision=revision,
        snapshot_path=str(snapshot),
        files=tuple(entries),
    )
