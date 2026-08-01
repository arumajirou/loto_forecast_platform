import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "sundial-base"

EVIDENCE_DIR = PROJECT_ROOT / "audit" / "tsfm-runtime" / MODEL_ID

STATUS_PATH = PROJECT_ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"

PROGRESS_PATH = PROJECT_ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_inference_passed() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["status"] == "PASS"
    assert result["model_id"] == MODEL_ID
    assert result["input_series_count"] == 7
    assert result["context_length"] == 64
    assert result["prediction_length"] == 1
    assert result["input_shape"] == [7, 64]
    assert result["output_shape"] == [7, 1, 1]
    assert result["output_finite"] is True

    assert result["parameter_device"] == "cuda:0"
    assert result["input_device"] == "cuda:0"
    assert result["output_device"] == "cuda:0"
    assert result["cpu_fallback"] is False

    assert result["peak_vram_bytes"] > 0
    assert result["inference_iterations"] >= 1
    assert len(result["prediction_values"]) == 7


def test_runtime_certification_passed() -> None:
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert certification["runtime_status"] == "CERTIFIED"
    assert certification["runtime_vram_certified"] is True
    assert certification["runtime_gpu_used"] is True
    assert certification["runtime_cpu_fallback"] is False

    checks = certification["checks"]
    assert checks
    assert all(checks.values())


def test_external_gpu_pid_evidence() -> None:
    runtime = _load_json(EVIDENCE_DIR / "runtime-result.json")
    gpu = _load_json(EVIDENCE_DIR / "external-gpu-pid-evidence.json")

    assert gpu["captured"] is True
    assert gpu["capture_count"] >= 1
    assert gpu["runtime_pid"] == runtime["pid"]
    assert gpu["max_gpu_memory_mib"] > 0
    assert gpu["min_gpu_memory_mib"] >= 0


def test_remote_code_and_license_reviews() -> None:
    remote_code = _load_json(EVIDENCE_DIR / "remote-code-review.json")
    license_review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert remote_code["review_status"] == "APPROVED"

    assert license_review["review_status"] == "APPROVED"
    assert license_review["license"].lower() == "apache-2.0"
    assert license_review["commercial_use"] is True


def test_ledger_and_summary_counts() -> None:
    status = _load_json(STATUS_PATH)

    assert len(status["results"]) == 21

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_gpu_used"] is True
    assert row["runtime_cpu_fallback"] is False

    certified = sum(item.get("runtime_status") == "CERTIFIED" for item in status["results"])
    blocked = sum(item.get("runtime_status") == "BLOCKED" for item in status["results"])
    pending = len(status["results"]) - certified - blocked

    assert certified == 9
    assert blocked == 12
    assert pending == 0

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
    text = PROGRESS_PATH.read_text(encoding="utf-8")

    assert "sundial-base" in text
    assert "9 / 21" in text
    assert "12" in text
    assert "42.9%" in text
    assert "NO_PENDING_MODELS" in text


def test_sha256_manifest() -> None:
    manifest_path = EVIDENCE_DIR / "sha256sum.txt"

    lines = manifest_path.read_text(encoding="utf-8").splitlines()

    assert lines

    for line in lines:
        digest, relative_name = line.split(maxsplit=1)

        relative_name = relative_name.lstrip("*")
        file_path = EVIDENCE_DIR / relative_name

        assert file_path.is_file(), relative_name

        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()

        assert actual == digest, relative_name
