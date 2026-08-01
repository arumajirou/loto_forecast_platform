from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit" / "tsfm-runtime" / "lag-llama"
LEDGER = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"

REVISION = "72dcfc29da106acfe38250a60f4ae29d1e56a3d9"
CHECKPOINT_SHA256 = "b5a5c4b8a0cfe9b81bdac35ed5d88b5033cd119b5206c28e9cd67c4b45fb2c96"


def load_json(name: str) -> dict:
    return json.loads((AUDIT / name).read_text(encoding="utf-8"))


def test_runtime_result_is_certified() -> None:
    result = load_json("runtime-result.json")

    assert result["status"] == "OK"
    assert result["revision"] == REVISION
    assert result["prediction_shape"] == [7]
    assert result["finite"] is True


def test_state_dict_loaded_exactly() -> None:
    result = load_json("runtime-result.json")

    assert result["checkpoint_state_entries"] == 73
    assert result["state_dict_missing_keys"] == []
    assert result["state_dict_unexpected_keys"] == []


def test_cuda_runtime_evidence() -> None:
    result = load_json("runtime-result.json")
    gpu = result["gpu_evidence"]

    assert gpu["requested_device"] == "cuda"
    assert gpu["execution_device"] == "cuda"
    assert gpu["cuda_available"] is True
    assert gpu["gpu_used"] is True
    assert gpu["cpu_fallback"] is False
    assert gpu["model_device"] == "cuda:0"
    assert gpu["peak_vram_bytes"] > 0
    assert gpu["gpu_pid"] is not None


def test_checkpoint_hash_is_pinned() -> None:
    result = load_json("runtime-result.json")
    properties = result["properties"]

    assert properties["checkpoint_sha256"] == CHECKPOINT_SHA256
    assert properties["checkpoint_size_bytes"] == 29488819


def test_runtime_certification() -> None:
    certification = load_json("runtime-certification.json")

    assert certification["runtime_status"] == "CERTIFIED"
    assert certification["runtime_vram_certified"] is True
    assert certification["runtime_gpu_used"] is True
    assert certification["runtime_cpu_fallback"] is False
    assert certification["checkpoint_sha256"] == CHECKPOINT_SHA256


def test_license_review_is_approved() -> None:
    review = load_json("license-review.json")

    assert review["license"] == "Apache-2.0"
    assert review["review_status"] == "APPROVED"
    assert review["commercial_use"] is True


def test_ledger_is_certified() -> None:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))

    row = next(item for item in data["results"] if item["model_id"] == "lag-llama")

    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_revision"] == REVISION
    assert row["runtime_cpu_fallback"] is False
    assert row["runtime_prediction_shape"] == [7]
    assert row["runtime_prediction_finite"] is True
    assert row["runtime_checkpoint_sha256"] == CHECKPOINT_SHA256


def test_predictions_are_finite() -> None:
    result = load_json("runtime-result.json")

    predictions = result["predictions"]

    assert len(predictions) == 7
    assert all(isinstance(value, int | float) for value in predictions)


def test_manifest_is_current() -> None:
    lines = (AUDIT / "sha256sum.txt").read_text(encoding="utf-8").splitlines()

    assert lines

    for line in lines:
        expected, filename = line.split("  ", 1)

        actual = hashlib.sha256((AUDIT / filename).read_bytes()).hexdigest()

        assert expected == actual


def test_accuracy_not_certified() -> None:
    certification = load_json("runtime-certification.json")

    assert certification["domain_compatibility_certified"] is False
    assert certification["accuracy_certified"] is False
