from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CheckpointIntegrityError(RuntimeError):
    """Raised before deserialization when checkpoint provenance is not trusted."""


class CheckpointGateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_filename: str = Field(min_length=1)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    local_files_only: bool = True


class CheckpointEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_path: str
    visible_checkpoint_path: str
    resolved_checkpoint_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    verified_before_load: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checkpoint_before_load(
    *,
    checkpoint_path: Path,
    snapshot_path: Path,
    repository_cache_root: Path,
    spec: CheckpointGateSpec,
) -> CheckpointEvidence:
    if not spec.local_files_only:
        raise CheckpointIntegrityError("local_files_only must be true")

    visible_checkpoint = checkpoint_path.absolute()
    visible_snapshot = snapshot_path.absolute()
    cache_root = repository_cache_root.resolve()

    if visible_snapshot.name != spec.expected_revision:
        raise CheckpointIntegrityError("snapshot directory does not match expected revision")
    if visible_checkpoint.name != spec.expected_filename:
        raise CheckpointIntegrityError("checkpoint filename does not match trusted manifest")
    if visible_checkpoint.parent != visible_snapshot:
        raise CheckpointIntegrityError("checkpoint must be directly visible in the fixed snapshot")
    if not visible_checkpoint.is_file():
        raise CheckpointIntegrityError(f"checkpoint does not exist: {visible_checkpoint}")

    resolved_checkpoint = visible_checkpoint.resolve(strict=True)
    blobs_root = (cache_root / "blobs").resolve()
    try:
        resolved_checkpoint.relative_to(blobs_root)
    except ValueError as exc:
        raise CheckpointIntegrityError(
            "checkpoint symlink target is outside the trusted repository cache"
        ) from exc

    actual_sha256 = sha256_file(visible_checkpoint)
    if actual_sha256 != spec.expected_sha256:
        raise CheckpointIntegrityError(
            "checkpoint SHA-256 mismatch: "
            f"expected={spec.expected_sha256}, actual={actual_sha256}"
        )

    size_bytes = visible_checkpoint.stat().st_size
    if size_bytes <= 0:
        raise CheckpointIntegrityError("checkpoint file is empty")

    return CheckpointEvidence(
        snapshot_path=str(visible_snapshot),
        visible_checkpoint_path=str(visible_checkpoint),
        resolved_checkpoint_path=str(resolved_checkpoint),
        sha256=actual_sha256,
        size_bytes=size_bytes,
        verified_before_load=True,
    )


def guarded_checkpoint_load(
    *,
    checkpoint_path: Path,
    snapshot_path: Path,
    repository_cache_root: Path,
    spec: CheckpointGateSpec,
    loader: Callable[[Path], T],
) -> tuple[T, CheckpointEvidence]:
    """Run the complete provenance gate before invoking any deserializer."""

    evidence = verify_checkpoint_before_load(
        checkpoint_path=checkpoint_path,
        snapshot_path=snapshot_path,
        repository_cache_root=repository_cache_root,
        spec=spec,
    )
    loaded = loader(checkpoint_path)
    return loaded, evidence


def formal_runtime_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if base is None else base)
    environment.update(
        {
            "TABPFN_DISABLE_TELEMETRY": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DO_NOT_TRACK": "1",
        }
    )
    return environment
