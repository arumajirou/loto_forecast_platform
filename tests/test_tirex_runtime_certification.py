import json
from pathlib import Path

RUNNER = Path("scripts/run_tirex_provider.py")
CERTIFICATION = Path("audit/tsfm-runtime/tirex-2/runtime-certification.json")
RUNTIME = Path("audit/tsfm-runtime/tirex-2/runtime-result.json")
PROVIDER_RESPONSE = Path("audit/tsfm-runtime/tirex-2/provider-response.json")
STATUS = Path("audit/tsfm-runtime/runtime-status.json")

REPO_ID = "NX-AI/TiRex-2"
REVISION = "05e5b26db52bfb256f1ae1bdf785589850482de3"


def test_tirex_runner_is_revision_pinned() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert f'REPO_ID = "{REPO_ID}"' in text
    assert f'REVISION = "{REVISION}"' in text
    assert 'hf_kwargs={"revision": revision, "local_files_only": True}' in text
    assert 'execution_device = "cuda"' in text


def test_tirex_runtime_certification_is_gpu_backed() -> None:
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))

    assert runtime["status"] == "PASS"
    assert runtime["runtime_vram_certified"] is True
    assert runtime["device"] == "cuda"
    assert runtime["peak_vram_bytes"] > 0
    assert runtime["finite"] is True
    assert runtime["prediction_shape"] == [7]
    assert runtime["quantile_shape"] == [7, 9, 1]


def test_tirex_provider_response_has_no_cpu_fallback() -> None:
    response = json.loads(PROVIDER_RESPONSE.read_text(encoding="utf-8"))
    gpu = response["gpu_evidence"]

    assert response["status"] == "OK"
    assert response["finite"] is True
    assert response["prediction_shape"] == [7]
    assert len(response["predictions"]) == 7
    assert gpu["requested_device"] == "cuda"
    assert gpu["execution_device"] == "cuda"
    assert gpu["gpu_used"] is True
    assert gpu["cpu_fallback"] is False
    assert gpu["resource_certification"] == "GPU_PASS"
    assert gpu["peak_vram_bytes"] > 0


def test_tirex_certification_has_fixed_artifacts() -> None:
    certification = json.loads(CERTIFICATION.read_text(encoding="utf-8"))

    assert certification["repo_id"] == REPO_ID
    assert certification["revision"] == REVISION
    assert certification["certification_status"] == "RUNTIME_CERTIFIED"
    assert certification["runtime_vram_certified"] is True
    assert certification["cpu_fallback"] is False
    assert certification["snapshot_complete"] is True
    assert certification["weight_sha256"]
    assert certification["config_sha256"]


def test_runtime_status_contains_four_certified_models() -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))

    row = next(item for item in status["results"] if item["model_id"] == "tirex-2")

    assert status["runtime_certified_models"] == 4
    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_revision"] == REVISION
    assert row["runtime_device"] == "cuda"
    assert row["runtime_cpu_fallback"] is False
    assert row["runtime_peak_vram_bytes"] > 0
