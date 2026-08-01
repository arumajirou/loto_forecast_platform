from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit" / "tsfm-runtime" / "toto-open-base"
LEDGER = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"

REVISION = "0411ceb27bdf7fc3e4892e99edc8ad08192dc3c5"
CONFIG_SHA256 = "e381ed28a05898bf2ea3386adb839f9f2742d66d97825db492b6658d4af1f778"
WEIGHT_SHA256 = "69b67e60decc90baf741729abcf1fe8fe0881e3e3337176042053c28a122fa4c"


def load_json(name: str) -> dict:
    return json.loads((AUDIT / name).read_text(encoding="utf-8"))


def test_runtime_result_is_ok() -> None:
    result = load_json("runtime-result.json")

    assert result["status"] == "OK"
    assert result["revision"] == REVISION
    assert result["model_class"] == "Toto"
    assert result["forecaster_class"] == "TotoForecaster"
    assert result["model_parameter_count"] == 151306080


def test_output_shapes() -> None:
    result = load_json("runtime-result.json")

    assert result["input_shape"] == [7, 512]
    assert result["sample_shape"] == [
        1,
        7,
        1,
        256,
    ]
    assert result["median_shape"] == [1, 7, 1]
    assert result["prediction_shape"] == [7]
    assert result["finite"] is True


def test_predictions_are_finite() -> None:
    result = load_json("runtime-result.json")
    predictions = result["predictions"]

    assert len(predictions) == 7
    assert all(isinstance(value, int | float) for value in predictions)
    assert all(math.isfinite(value) for value in predictions)


def test_snapshot_hashes() -> None:
    properties = load_json("runtime-result.json")["properties"]

    assert properties["config_sha256"] == CONFIG_SHA256
    assert properties["weight_sha256"] == WEIGHT_SHA256
    assert properties["weight_size_bytes"] == 605239264
    assert properties["snapshot_complete"] is True


def test_cuda_evidence() -> None:
    gpu = load_json("runtime-result.json")["gpu_evidence"]

    assert gpu["requested_device"] == "cuda"
    assert gpu["execution_device"] == "cuda"
    assert gpu["cuda_available"] is True
    assert gpu["gpu_used"] is True
    assert gpu["cpu_fallback"] is False
    assert gpu["model_device"] == "cuda:0"
    assert gpu["output_device"] == "cuda:0"
    assert gpu["peak_vram_bytes"] > 0
    assert gpu["gpu_pid"] is not None


def test_runtime_certification() -> None:
    certification = load_json("runtime-certification.json")

    assert certification["runtime_status"] == "CERTIFIED"
    assert certification["runtime_vram_certified"] is True
    assert certification["runtime_gpu_used"] is True
    assert certification["runtime_cpu_fallback"] is False
    assert certification["weight_sha256"] == WEIGHT_SHA256


def test_license_review() -> None:
    review = load_json("license-review.json")

    assert review["license"] == "Apache-2.0"
    assert review["review_status"] == "APPROVED"
    assert review["commercial_use"] is True


def test_ledger_is_certified() -> None:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))

    row = next(item for item in data["results"] if item["model_id"] == "toto-open-base")

    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_revision"] == REVISION
    assert row["runtime_cpu_fallback"] is False
    assert row["runtime_prediction_shape"] == [7]
    assert row["runtime_sample_shape"] == [1, 7, 1, 256]
    assert row["runtime_weight_sha256"] == WEIGHT_SHA256


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
