from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.neuralforecast.auto_timellm.contracts import (
    ArchitectureProfile,
    PinnedLLMIdentity,
    SnapshotFileEvidence,
    TrialParameters,
    load_snapshot_model_metadata,
    resolve_architecture,
    verify_snapshot,
)

REVISION = "a" * 40


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(tmp_path: Path, *, auto_map: bool = False) -> PinnedLLMIdentity:
    root = tmp_path / REVISION
    root.mkdir()
    config = {
        "architectures": ["GPT2Model"],
        "model_type": "gpt2",
        "n_embd": 64,
        "n_layer": 2,
    }
    if auto_map:
        config["auto_map"] = {"AutoModel": "modeling_custom.CustomModel"}
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "tokenizer.json").write_text("{}", encoding="utf-8")
    (root / "model.safetensors").write_bytes(b"weights")
    records = []
    for name in ("config.json", "tokenizer.json", "model.safetensors"):
        path = root / name
        records.append(
            SnapshotFileEvidence(
                relative_path=name,
                sha256=_hash(path),
                size_bytes=path.stat().st_size,
            )
        )
    return PinnedLLMIdentity(
        repo_id="openai-community/gpt2",
        revision=REVISION,
        snapshot_path=str(root),
        license_id="MIT",
        files=tuple(records),
    )


def test_snapshot_verification_and_metadata(tmp_path: Path) -> None:
    identity = _snapshot(tmp_path)
    verification = verify_snapshot(identity)
    metadata = load_snapshot_model_metadata(identity)
    assert verification.status == "PASS"
    assert verification.file_count == 3
    assert metadata.hidden_size == 64
    assert metadata.num_hidden_layers == 2
    assert metadata.model_type == "gpt2"


def test_snapshot_tamper_is_rejected(tmp_path: Path) -> None:
    identity = _snapshot(tmp_path)
    (Path(identity.snapshot_path) / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="identity mismatch"):
        verify_snapshot(identity)


def test_custom_code_auto_map_is_rejected(tmp_path: Path) -> None:
    identity = _snapshot(tmp_path, auto_map=True)
    with pytest.raises(ValueError, match="auto_map"):
        verify_snapshot(identity)


def test_unlisted_snapshot_file_is_rejected(tmp_path: Path) -> None:
    identity = _snapshot(tmp_path)
    (Path(identity.snapshot_path) / "unexpected.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory mismatch"):
        verify_snapshot(identity)


def test_unsafe_and_mutable_identity_is_rejected(tmp_path: Path) -> None:
    identity = _snapshot(tmp_path)
    payload = identity.model_dump(mode="json")
    payload["revision"] = "main"
    with pytest.raises(ValidationError, match="immutable"):
        PinnedLLMIdentity.model_validate(payload)
    with pytest.raises(ValidationError, match="unsafe"):
        SnapshotFileEvidence(
            relative_path="../config.json",
            sha256="0" * 64,
            size_bytes=1,
        )


def test_architecture_profiles_are_geometry_safe() -> None:
    for profile in ArchitectureProfile:
        spec = resolve_architecture(5, profile)
        assert spec.patch_len <= spec.input_size
        assert spec.stride <= spec.patch_len
        assert spec.d_model % spec.n_heads == 0


def test_trial_schedule_rejects_validation_after_training() -> None:
    with pytest.raises(ValidationError, match="val_check_steps"):
        TrialParameters(
            architecture_profile=ArchitectureProfile.COMPACT,
            learning_rate=1e-4,
            max_steps=10,
            val_check_steps=20,
            batch_size=8,
            windows_batch_size=32,
            dropout=0.1,
            scaler_type="identity",
            random_seed=1,
        )
