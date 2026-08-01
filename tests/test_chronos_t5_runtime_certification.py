import json
from pathlib import Path

RUNNER = Path("scripts/run_chronos_t5_provider.py")
PROVIDER = Path("src/loto/models/providers/chronos.py")
CATALOG = Path("src/loto/models/catalog.py")
REGISTRY = Path("src/loto/models/providers/registry.py")
CERTIFICATION = Path("audit/tsfm-runtime/chronos-t5-small/runtime-certification.json")
RUNTIME = Path("audit/tsfm-runtime/chronos-t5-small/runtime-result.json")
RESPONSE = Path("audit/tsfm-runtime/chronos-t5-small/provider-response.json")
STATUS = Path("audit/tsfm-runtime/runtime-status.json")

MODEL_ID = "chronos-t5-small"
REPO_ID = "amazon/chronos-t5-small"
REVISION = "a971ba21945c4f1796b17a91fe69214b5f4ad472"
WEIGHT_SHA256 = "9c8b6fde5300f72b01c173153bf9288fa0a200614275bf0585071ad71a6a3d43"
CONFIG_SHA256 = "76b7445a93491851e434733a138b67e26eda4375f83e08f80a07383c6b3f571a"
GENERATION_CONFIG_SHA256 = "8f6833851ce53496a43ef87a975c766f7a3049e2d598ecef609a526ca6308534"


def test_chronos_t5_runner_is_fail_closed() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert f'MODEL_ID = "{MODEL_ID}"' in text
    assert f'REPO_ID = "{REPO_ID}"' in text
    assert f'REVISION = "{REVISION}"' in text
    assert "local_files_only must be true" in text
    assert "requires cuda" in text
    assert "snapshot_path is required" in text
    assert "snapshot file target is outside" in text
    assert "prediction_length must be 1" in text
    assert "num_samples must be 20" in text
    assert "seed must be 42" in text


def test_chronos_provider_uses_t5_runner() -> None:
    text = PROVIDER.read_text(encoding="utf-8")

    assert "CHRONOS_T5_RUNNER" in text
    assert "def _is_chronos_t5_small" in text
    assert "def _fixed_t5_snapshot_path" in text
    assert "def _run_t5_provider" in text
    assert "runtime_response" in text
    assert "subprocess.run" in text


def test_chronos_t5_catalog_and_registry() -> None:
    catalog = CATALOG.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")

    assert MODEL_ID in catalog
    assert REPO_ID in catalog
    assert REVISION in catalog
    assert "ChronosPipeline" in catalog
    assert f'"{MODEL_ID}": ChronosProvider' in registry


def test_chronos_t5_runtime_is_gpu_backed() -> None:
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))

    assert runtime["status"] == "PASS"
    assert runtime["runtime_vram_certified"] is True
    assert runtime["device"].startswith("cuda")
    assert runtime["input_device"] == "cpu"
    assert runtime["tokenizer_device"] == "cpu"
    assert runtime["cpu_preprocessing"] is True
    assert runtime["cpu_fallback"] is False
    assert runtime["peak_vram_bytes"] > 0
    assert runtime["prediction_shape"] == [7]
    assert runtime["quantile_shape"] == [7, 1, 9]
    assert runtime["mean_shape"] == [7, 1]
    assert runtime["finite"] is True


def test_chronos_t5_response_uses_fixed_artifact() -> None:
    response = json.loads(RESPONSE.read_text(encoding="utf-8"))

    gpu = response["gpu_evidence"]
    properties = response["properties"]
    artifact = response["artifact_reference"]

    assert response["status"] == "OK"
    assert response["prediction_shape"] == [7]
    assert response["quantile_shape"] == [7, 1, 9]
    assert response["mean_shape"] == [7, 1]
    assert len(response["predictions"]) == 7
    assert response["finite"] is True

    assert gpu["requested_device"] == "cuda"
    assert gpu["execution_device"].startswith("cuda")
    assert gpu["model_device"].startswith("cuda")
    assert gpu["input_device"] == "cpu"
    assert gpu["tokenizer_device"] == "cpu"
    assert gpu["gpu_used"] is True
    assert gpu["cpu_preprocessing"] is True
    assert gpu["cpu_fallback"] is False
    assert gpu["resource_certification"] == "GPU_PASS"
    assert gpu["peak_vram_bytes"] > 0

    assert artifact["repo_id"] == REPO_ID
    assert artifact["revision"] == REVISION
    assert properties["weight_sha256"] == WEIGHT_SHA256
    assert properties["config_sha256"] == CONFIG_SHA256
    assert properties["generation_config_sha256"] == GENERATION_CONFIG_SHA256
    assert properties["pipeline_class"] == "ChronosPipeline"
    assert properties["model_class"] == "ChronosModel"
    assert properties["num_samples"] == 20
    assert properties["seed"] == 42


def test_chronos_t5_license_is_recorded() -> None:
    certification = json.loads(CERTIFICATION.read_text(encoding="utf-8"))

    assert certification["license"] == "Apache-2.0"
    assert certification["license_commercial_use"] is True
    assert certification["license_review_status"] == "APPROVED"
    assert certification["license_attribution_required"] is True


def test_runtime_status_contains_seven_certified_models() -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert status["runtime_certified_models"] == 7
    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_revision"] == REVISION
    assert row["runtime_device"].startswith("cuda")
    assert row["runtime_input_device"] == "cpu"
    assert row["runtime_cpu_preprocessing"] is True
    assert row["runtime_cpu_fallback"] is False
