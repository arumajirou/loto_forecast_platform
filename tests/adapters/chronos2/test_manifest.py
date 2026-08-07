from __future__ import annotations

from pathlib import Path

import pytest

from loto.adapters.chronos2.manifest import (
    CHRONOS_MODEL_REVISION,
    build_model_manifest,
)


def make_snapshot(root: Path) -> Path:
    snapshot = root / CHRONOS_MODEL_REVISION
    snapshot.mkdir()
    (snapshot / "config.json").write_text('{"model_type":"chronos2"}\n', encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"test-weight")
    (snapshot / "README.md").write_text("test\n", encoding="utf-8")
    return snapshot


def test_manifest_hashes_snapshot_files(tmp_path: Path) -> None:
    snapshot = make_snapshot(tmp_path)
    manifest = build_model_manifest(snapshot, lane="current_reviewed")
    assert manifest.status == "VERIFIED"
    assert manifest.revision == CHRONOS_MODEL_REVISION
    assert {item.path for item in manifest.files} == {
        "README.md",
        "config.json",
        "model.safetensors",
    }
    assert all(len(item.sha256) == 64 for item in manifest.files)


def test_manifest_requires_weights(tmp_path: Path) -> None:
    snapshot = tmp_path / CHRONOS_MODEL_REVISION
    snapshot.mkdir()
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="model.safetensors"):
        build_model_manifest(snapshot, lane="legacy_reproduction")


def test_unreviewed_revision_is_rejected(tmp_path: Path) -> None:
    snapshot = make_snapshot(tmp_path)
    with pytest.raises(ValueError, match="reviewed model revision"):
        build_model_manifest(snapshot, lane="current_reviewed", revision="0" * 40)
