from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from loto.adapters.tabpfn_ts import (
    CheckpointGateSpec,
    CheckpointIntegrityError,
    formal_runtime_environment,
    guarded_checkpoint_load,
    verify_checkpoint_before_load,
)

REVISION = "1" * 40
FILENAME = "trusted.ckpt"


def _checkpoint_tree(
    tmp_path: Path, content: bytes = b"trusted checkpoint"
) -> tuple[Path, Path, Path]:
    cache_root = tmp_path / "models--example--tabpfn"
    blobs = cache_root / "blobs"
    snapshot = cache_root / "snapshots" / REVISION
    blobs.mkdir(parents=True)
    snapshot.mkdir(parents=True)
    blob = blobs / "blob-id"
    blob.write_bytes(content)
    visible = snapshot / FILENAME
    visible.symlink_to(blob)
    return cache_root, snapshot, visible


def test_hash_is_verified_before_loader_is_called(tmp_path: Path) -> None:
    cache_root, snapshot, visible = _checkpoint_tree(tmp_path)
    expected = hashlib.sha256(visible.read_bytes()).hexdigest()
    spec = CheckpointGateSpec(
        expected_filename=FILENAME,
        expected_sha256=expected,
        expected_revision=REVISION,
    )
    events: list[str] = []

    def loader(path: Path) -> str:
        events.append("loader-called")
        return path.name

    loaded, evidence = guarded_checkpoint_load(
        checkpoint_path=visible,
        snapshot_path=snapshot,
        repository_cache_root=cache_root,
        spec=spec,
        loader=loader,
    )
    assert loaded == FILENAME
    assert events == ["loader-called"]
    assert evidence.verified_before_load is True
    assert evidence.sha256 == expected


def test_hash_mismatch_prevents_deserialization(tmp_path: Path) -> None:
    cache_root, snapshot, visible = _checkpoint_tree(tmp_path)
    spec = CheckpointGateSpec(
        expected_filename=FILENAME,
        expected_sha256="0" * 64,
        expected_revision=REVISION,
    )
    events: list[str] = []

    def loader(_: Path) -> object:
        events.append("unsafe-loader-called")
        return object()

    with pytest.raises(CheckpointIntegrityError, match="SHA-256 mismatch"):
        guarded_checkpoint_load(
            checkpoint_path=visible,
            snapshot_path=snapshot,
            repository_cache_root=cache_root,
            spec=spec,
            loader=loader,
        )
    assert events == []


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    cache_root = tmp_path / "models--example--tabpfn"
    snapshot = cache_root / "snapshots" / REVISION
    snapshot.mkdir(parents=True)
    outside = tmp_path / "outside.ckpt"
    outside.write_bytes(b"outside")
    visible = snapshot / FILENAME
    visible.symlink_to(outside)
    expected = hashlib.sha256(outside.read_bytes()).hexdigest()
    spec = CheckpointGateSpec(
        expected_filename=FILENAME,
        expected_sha256=expected,
        expected_revision=REVISION,
    )
    with pytest.raises(CheckpointIntegrityError, match="outside the trusted repository cache"):
        verify_checkpoint_before_load(
            checkpoint_path=visible,
            snapshot_path=snapshot,
            repository_cache_root=cache_root,
            spec=spec,
        )


def test_revision_and_filename_are_fail_closed(tmp_path: Path) -> None:
    cache_root, snapshot, visible = _checkpoint_tree(tmp_path)
    expected = hashlib.sha256(visible.read_bytes()).hexdigest()
    wrong_revision = CheckpointGateSpec(
        expected_filename=FILENAME,
        expected_sha256=expected,
        expected_revision="2" * 40,
    )
    with pytest.raises(CheckpointIntegrityError, match="expected revision"):
        verify_checkpoint_before_load(
            checkpoint_path=visible,
            snapshot_path=snapshot,
            repository_cache_root=cache_root,
            spec=wrong_revision,
        )


def test_formal_environment_disables_networked_behaviors() -> None:
    environment = formal_runtime_environment({"EXISTING": "1"})
    assert environment["EXISTING"] == "1"
    assert environment["TABPFN_DISABLE_TELEMETRY"] == "1"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["DO_NOT_TRACK"] == "1"
