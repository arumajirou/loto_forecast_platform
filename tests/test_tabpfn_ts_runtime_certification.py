import json
from pathlib import Path

RUNNER = Path("scripts/run_tabpfn_ts_provider.py")
PROVIDER = Path("src/loto/models/providers/tabpfn_ts.py")
PINS = Path("configs/tsfm/verified-revisions.json")
STATIC_AUDIT = Path("audit/tsfm-static/static-audit.json")
CERTIFICATION = Path("audit/tsfm-runtime/tabpfn-ts/runtime-certification.json")
RUNTIME = Path("audit/tsfm-runtime/tabpfn-ts/runtime-result.json")
RESPONSE = Path("audit/tsfm-runtime/tabpfn-ts/provider-response.json")
STATUS = Path("audit/tsfm-runtime/runtime-status.json")

REPO_ID = "Prior-Labs/TabPFN-v2-reg"
REVISION = "4972a65a1b30806315c6f92499959ffbfc69a673"
WEIGHT = "tabpfn-v2-regressor.ckpt"


def test_tabpfn_runner_is_fail_closed() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert f'REPO_ID = "{REPO_ID}"' in text
    assert f'REVISION = "{REVISION}"' in text
    assert f'WEIGHT_FILENAME = "{WEIGHT}"' in text
    assert "unsupported revision" in text
    assert "local_files_only must be true" in text
    assert "snapshot_path is required" in text
    assert "checkpoint symlink target is outside" in text
    assert "resolve_model_path" not in text


def test_tabpfn_provider_uses_fixed_snapshot() -> None:
    text = PROVIDER.read_text(encoding="utf-8")

    assert "def _fixed_snapshot_path" in text
    assert "models--Prior-Labs--TabPFN-v2-reg" in text
    assert '"snapshot_path": str(' in text


def test_tabpfn_identity_is_consistent() -> None:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    static = json.loads(STATIC_AUDIT.read_text(encoding="utf-8"))

    pin = next(row for row in pins["pins"] if row["model_id"] == "tabpfn-ts")
    audit = next(row for row in static["results"] if row["model_id"] == "tabpfn-ts")

    for row in (pin, audit):
        assert row["repo_id"] == REPO_ID
        assert row["revision"] == REVISION

    assert audit["pipeline_tag"] == "tabular-regression"
    assert audit["weight_files"] == [WEIGHT]
    assert "tabular-classification" not in audit["tags"]


def test_tabpfn_runtime_is_gpu_backed() -> None:
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))

    assert runtime["status"] == "PASS"
    assert runtime["runtime_vram_certified"] is True
    assert runtime["device"] == "cuda"
    assert runtime["peak_vram_bytes"] > 0
    assert runtime["prediction_shape"] == [37]
    assert runtime["finite"] is True


def test_tabpfn_response_uses_fixed_artifact() -> None:
    response = json.loads(RESPONSE.read_text(encoding="utf-8"))

    gpu = response["gpu_evidence"]
    properties = response["properties"]
    artifact = response["artifact_reference"]

    assert response["status"] == "OK"
    assert response["prediction_shape"] == [37]
    assert len(response["predictions"]) == 37
    assert response["finite"] is True

    assert gpu["requested_device"] == "cuda"
    assert gpu["execution_device"] == "cuda"
    assert gpu["gpu_used"] is True
    assert gpu["cpu_fallback"] is False
    assert gpu["resource_certification"] == "GPU_PASS"
    assert gpu["peak_vram_bytes"] > 0

    assert artifact["repo_id"] == REPO_ID
    assert artifact["revision"] == REVISION
    assert properties["weight_path"].endswith(f"{REVISION}/{WEIGHT}")
    assert properties["weight_sha256"]
    assert properties["config_sha256"]


def test_tabpfn_license_is_recorded() -> None:
    certification = json.loads(CERTIFICATION.read_text(encoding="utf-8"))

    assert certification["license_review_status"] == "APPROVED_WITH_ATTRIBUTION"
    assert certification["license_commercial_use"] is True
    assert certification["license_attribution_required"] is True


def test_runtime_status_contains_five_certified_models() -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))

    row = next(item for item in status["results"] if item["model_id"] == "tabpfn-ts")

    assert status["runtime_certified_models"] == sum(
        item.get("runtime_status") == "CERTIFIED" for item in status["results"]
    )
    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_revision"] == REVISION
    assert row["runtime_device"] == "cuda"
    assert row["runtime_cpu_fallback"] is False
