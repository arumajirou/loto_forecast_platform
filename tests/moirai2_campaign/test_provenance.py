from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loto.moirai2_campaign.model_manifest import (
    MODEL_CONFIG_SHA256,
    MODEL_REVISION,
    MODEL_WEIGHT_SHA256,
    UNI2TS_SDIST_SHA256,
    UNI2TS_VERSION,
    UNI2TS_WHEEL_SHA256,
)
from loto.moirai2_campaign.provenance import ProvenanceError, verify_snapshot


def _official_config_bytes() -> bytes:
    payload = {
        "attn_dropout_p": 0,
        "d_ff": 1024,
        "d_model": 384,
        "dropout_p": 0,
        "max_seq_len": 512,
        "num_layers": 6,
        "num_predict_token": 4,
        "patch_size": 16,
        "quantile_levels": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "scaling": True,
    }
    return json.dumps(payload, indent=2).encode("utf-8")


def test_frozen_package_and_config_hashes() -> None:
    assert UNI2TS_VERSION == "2.0.0"
    assert UNI2TS_WHEEL_SHA256 == (
        "7bb185392885e3f0cb53773a5fb0b922d99bf56e93790332d23abb3a4fa01612"
    )
    assert UNI2TS_SDIST_SHA256 == (
        "184b386db71a92f94a8961c1010fbcc126814b873faabc6a76ed680579c8d4be"
    )
    assert hashlib.sha256(_official_config_bytes()).hexdigest() == MODEL_CONFIG_SHA256
    assert MODEL_WEIGHT_SHA256 == (
        "fb5652a3db8ea572606221b7cb1e77bb8962b168e4d4cc752cf31ceb04074669"
    )


def test_snapshot_revision_and_hashes_fail_closed(tmp_path: Path) -> None:
    snapshot = tmp_path / MODEL_REVISION
    snapshot.mkdir()
    (snapshot / "config.json").write_bytes(_official_config_bytes())
    (snapshot / "model.safetensors").write_bytes(b"not-the-real-model")
    with pytest.raises(ProvenanceError, match="weight SHA-256"):
        verify_snapshot(snapshot)
