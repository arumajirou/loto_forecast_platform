import json
from pathlib import Path

RUNNER = Path("scripts/run_chronos_bolt_provider.py")
PROVIDER = Path("src/loto/models/providers/chronos.py")
CATALOG = Path("src/loto/models/catalog.py")
CERTIFICATION = Path("audit/tsfm-runtime/chronos-bolt-tiny/runtime-certification.json")
RUNTIME = Path("audit/tsfm-runtime/chronos-bolt-tiny/runtime-result.json")
RESPONSE = Path("audit/tsfm-runtime/chronos-bolt-tiny/provider-response.json")
STATUS = Path("audit/tsfm-runtime/runtime-status.json")

MODEL_ID = "chronos-bolt-tiny"
REPO_ID = "amazon/chronos-bolt-tiny"
REVISION = "a0e552de83495b5c28c14c71c374f3e33280b340"
WEIGHT_SHA256 = "75068728d376d2bec670379eeef4bfb4d24c0cfe24d957451f8d19b447030a32"
CONFIG_SHA256 = "278f0086733031635fb1c861cb01c1bad6477420c7fcb19381a2993e335785e0"


def test_chronos_bolt_runner_is_fail_closed() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert f'MODEL_ID = "{MODEL_ID}"' in text
    assert f'REPO_ID = "{REPO_ID}"' in text
    assert f'REVISION = "{REVISION}"' in text
    assert "local_files_only must be true" in text
    assert "requires cuda" in text
    assert "snapshot_path is required" in text
    assert "snapshot file target is outside" in text
    assert "prediction_length must be 1" in text


def test_chronos_provider_uses_subprocess_runner() -> None:
    text = PROVIDER.read_text(encoding="utf-8")

    assert "CHRONOS_BOLT_RUNNER" in text
    assert "def _fixed_bolt_snapshot_path" in text
    assert "def _run_bolt_provider" in text
    assert "runtime_response" in text
    assert "subprocess.run" in text


def test_chronos_catalog_is_pinned() -> None:
    text = CATALOG.read_text(encoding="utf-8")

    assert MODEL_ID in text
    assert REPO_ID in text
    assert REVISION in text
    assert "ChronosBoltPipeline" in text


def test_chronos_runtime_is_gpu_backed() -> None:
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))

    assert runtime["status"] == "PASS"
    assert runtime["runtime_vram_certified"] is True
    assert runtime["device"].startswith("cuda")
    assert runtime["peak_vram_bytes"] > 0
    assert runtime["prediction_shape"] == [7]
    assert runtime["quantile_shape"] == [7, 1, 9]
    assert runtime["mean_shape"] == [7, 1]
    assert runtime["finite"] is True


def test_chronos_response_uses_fixed_artifact() -> None:
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
    assert gpu["gpu_used"] is True
    assert gpu["cpu_fallback"] is False
    assert gpu["resource_certification"] == "GPU_PASS"
    assert gpu["peak_vram_bytes"] > 0

    assert artifact["repo_id"] == REPO_ID
    assert artifact["revision"] == REVISION
    assert properties["weight_sha256"] == WEIGHT_SHA256
    assert properties["config_sha256"] == CONFIG_SHA256
    assert properties["pipeline_class"] == "ChronosBoltPipeline"
    assert properties["model_class"] == "ChronosBoltModelForForecasting"


def test_chronos_license_is_recorded() -> None:
    certification = json.loads(CERTIFICATION.read_text(encoding="utf-8"))

    assert certification["license"] == "Apache-2.0"
    assert certification["license_commercial_use"] is True
    assert certification["license_review_status"] == "APPROVED"
    assert certification["license_attribution_required"] is True


def test_runtime_status_contains_six_certified_models() -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert status["runtime_certified_models"] == 6
    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_revision"] == REVISION
    assert row["runtime_device"].startswith("cuda")
    assert row["runtime_cpu_fallback"] is False
