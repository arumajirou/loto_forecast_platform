from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loto.moirai2_campaign.model_manifest import (
    MODEL_CONFIG_SHA256,
    MODEL_REVISION,
    MODEL_WEIGHT_SHA256,
    UNI2TS_VERSION,
)


class ProvenanceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_snapshot(snapshot_path: Path) -> dict[str, Any]:
    if not snapshot_path.is_dir():
        raise ProvenanceError(f"snapshot directory is missing: {snapshot_path}")
    if snapshot_path.name != MODEL_REVISION:
        raise ProvenanceError(
            f"snapshot revision mismatch: expected={MODEL_REVISION}, actual={snapshot_path.name}"
        )
    config_path = snapshot_path / "config.json"
    weight_path = snapshot_path / "model.safetensors"
    if not config_path.is_file() or not weight_path.is_file():
        raise ProvenanceError("config.json and model.safetensors are required")
    config_sha256 = sha256_file(config_path)
    weight_sha256 = sha256_file(weight_path)
    if config_sha256 != MODEL_CONFIG_SHA256:
        raise ProvenanceError("model config SHA-256 mismatch")
    if weight_sha256 != MODEL_WEIGHT_SHA256:
        raise ProvenanceError("model weight SHA-256 mismatch")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected_config = {
        "patch_size": 16,
        "max_seq_len": 512,
        "num_predict_token": 4,
        "quantile_levels": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "scaling": True,
    }
    for key, expected in expected_config.items():
        if config.get(key) != expected:
            raise ProvenanceError(f"model config value mismatch for {key}")
    return {
        "snapshot_path": str(snapshot_path),
        "model_revision": MODEL_REVISION,
        "config_path": str(config_path),
        "config_sha256": config_sha256,
        "weight_path": str(weight_path),
        "weight_sha256": weight_sha256,
        "uni2ts_version_expected": UNI2TS_VERSION,
    }
