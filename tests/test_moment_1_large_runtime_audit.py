import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "moment-1-large"

EVIDENCE_DIR = PROJECT_ROOT / "audit" / "tsfm-runtime" / MODEL_ID

STATUS_PATH = PROJECT_ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"

PROGRESS_PATH = PROJECT_ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_inference_passed() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["status"] == "PASS"
    assert result["model_id"] == MODEL_ID
    assert result["repo_id"] == "AutonLab/MOMENT-1-large"
    assert result["revision"] == ("ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc")

    assert result["input_series_count"] == 7
    assert result["context_length"] == 512
    assert result["prediction_length"] == 1
    assert result["prediction_shape"] == [7, 1, 1]
    assert len(result["prediction_values"]) == 7
    assert result["output_finite"] is True

    assert result["parameter_device"] == "cuda:0"
    assert result["input_device"] == "cuda:0"
    assert result["output_device"] == "cuda:0"
    assert result["runtime_gpu_used"] is True
    assert result["runtime_cpu_fallback"] is False
    assert result["peak_vram_bytes"] > 0


def test_execution_only_scope() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["runtime_certification_scope"] == "EXECUTION_ONLY"
    assert result["forecast_head_status"] == "FINE_TUNING_REQUIRED"
    assert result["forecast_head_pretrained"] is False
    assert result["forecast_accuracy_certified"] is False


def test_runtime_certification_passed() -> None:
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert certification["runtime_status"] == "CERTIFIED"
    assert certification["runtime_vram_certified"] is True
    assert certification["runtime_gpu_used"] is True
    assert certification["runtime_cpu_fallback"] is False
    assert certification["runtime_certification_scope"] == "EXECUTION_ONLY"
    assert certification["forecast_head_status"] == "FINE_TUNING_REQUIRED"
    assert certification["forecast_accuracy_certified"] is False
    assert all(certification["checks"].values())


def test_external_gpu_pid_evidence() -> None:
    runtime = _load_json(EVIDENCE_DIR / "runtime-result.json")
    gpu = _load_json(EVIDENCE_DIR / "external-gpu-pid-evidence.json")

    assert gpu["captured"] is True
    assert gpu["capture_count"] >= 1
    assert gpu["runtime_pid"] == runtime["runtime_pid"]
    assert gpu["max_gpu_memory_mib"] > 0
    assert gpu["min_gpu_memory_mib"] >= 0


def test_license_review_is_approved() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["review_status"] == "APPROVED"
    assert review["license"].lower() == "mit"
    assert review["commercial_use"] is True


def test_runtime_status_ledger_is_certified() -> None:
    status = _load_json(STATUS_PATH)

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_gpu_used"] is True
    assert row["runtime_cpu_fallback"] is False
    assert row["runtime_certification_scope"] == "EXECUTION_ONLY"
    assert row["forecast_head_status"] == "FINE_TUNING_REQUIRED"
    assert row["forecast_accuracy_certified"] is False

    assert status["runtime_certified_models"] == sum(
        item.get("runtime_status") == "CERTIFIED" for item in status["results"]
    )
    assert status["blocked_models"] == sum(
        item.get("runtime_status") == "BLOCKED" for item in status["results"]
    )
    assert status["pending_models"] == sum(
        item.get("runtime_status") not in {"CERTIFIED", "BLOCKED"} for item in status["results"]
    )


def test_progress_document() -> None:
    docs = PROGRESS_PATH.read_text(encoding="utf-8")

    assert "### moment-1-large" in docs
    assert "status: CERTIFIED" in docs
    assert "- Total models: 21" in docs
    assert "runtime certification scope: EXECUTION_ONLY" in docs
    assert "forecast head: FINE_TUNING_REQUIRED" in docs
    assert "forecast accuracy certified: false" in docs


def test_sha256_manifest() -> None:
    manifest = (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()

    assert manifest

    for line in manifest:
        digest, name = line.split(maxsplit=1)
        name = name.lstrip("*")
        path = EVIDENCE_DIR / name

        assert path.is_file(), name

        actual = hashlib.sha256(path.read_bytes()).hexdigest()

        assert actual == digest, name
