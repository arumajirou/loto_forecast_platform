from __future__ import annotations

from pathlib import Path

import pytest

from loto.merlion_campaign.artifacts import build_model_manifest, verify_model_manifest


def test_manifest_detects_mutation(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    model_file = model_dir / "model.pkl"
    model_file.write_bytes(b"trusted-local-model")
    (model_dir / "config.json").write_text("{}\n", encoding="utf-8")
    _, manifest_sha = build_model_manifest(
        model_dir,
        request_id="case-1",
        model_name="Arima",
        config={},
    )
    verified = verify_model_manifest(model_dir, manifest_sha)
    assert verified["trust_scope"] == "caller_controlled_work_root"
    model_file.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="mismatch"):
        verify_model_manifest(model_dir, manifest_sha)


def test_manifest_rejects_unlisted_file(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.pkl").write_bytes(b"trusted-local-model")
    (model_dir / "config.json").write_text("{}\n", encoding="utf-8")
    _, manifest_sha = build_model_manifest(
        model_dir,
        request_id="case-2",
        model_name="ETS",
        config={},
    )
    (model_dir / "unexpected.bin").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="inventory"):
        verify_model_manifest(model_dir, manifest_sha)
