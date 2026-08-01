from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_ID = "toto-2.0-4m"
REPO_ID = "Datadog/Toto-2.0-4m"
REVISION = "8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9"
CODE_REVISION = "44ea4e88852228039564aa3e76fac26aafac0803"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID

STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"

DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_toto_runtime_result_passed() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["status"] == "PASS"
    assert result["model_id"] == MODEL_ID
    assert result["repo_id"] == REPO_ID
    assert result["revision"] == REVISION
    assert result["code_revision"] == CODE_REVISION

    assert result["input_shape"] == [1, 7, 512]
    assert result["output_shape"] == [9, 1, 7, 1]
    assert result["output_finite"] is True
    assert len(result["median_predictions"]) == 7


def test_toto_model_properties() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["model_class"] == "Toto2Model"
    assert result["model_parameter_count"] == 4144448
    assert result["batch_size"] == 1
    assert result["series_count"] == 7
    assert result["context_length"] == 512
    assert result["horizon"] == 1
    assert result["quantile_count"] == 9
    assert result["decode_block_size"] == 32


def test_toto_cuda_evidence() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["model_device"] == "cuda:0"
    assert result["output_device"] == "cuda:0"
    assert result["runtime_gpu_used"] is True
    assert result["runtime_cpu_fallback"] is False
    assert result["peak_vram_bytes"] > 0


def test_toto_full_inference_scope() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["runtime_certification_scope"] == "FULL_INFERENCE"
    assert result["probabilistic_forecast_executed"] is True
    assert result["native_domain_contract_used"] is True
    assert result["lottery_domain_compatibility_certified"] is False
    assert result["forecast_accuracy_certified"] is False


def test_toto_runtime_environment() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    environment = result["runtime_environment"]

    assert environment["python_version"].startswith("3.12.")
    assert environment["toto_models_version"] == "1.0.0"
    assert environment["toto_2_version"] == "2.0.0"
    assert environment["torch_version"].startswith("2.13.0")
    assert environment["torch_cuda_version"] == "13.0"


def test_toto_runtime_certification() -> None:
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert certification["runtime_status"] == "CERTIFIED"
    assert certification["runtime_vram_certified"] is True
    assert certification["runtime_gpu_used"] is True
    assert certification["runtime_cpu_fallback"] is False
    assert certification["runtime_certification_scope"] == "FULL_INFERENCE"
    assert certification["probabilistic_forecast_executed"] is True
    assert certification["native_domain_contract_used"] is True
    assert certification["lottery_domain_compatibility_certified"] is False
    assert certification["forecast_accuracy_certified"] is False
    assert all(certification["checks"].values())


def test_toto_external_gpu_pid() -> None:
    runtime = _load_json(EVIDENCE_DIR / "runtime-result.json")

    gpu = _load_json(EVIDENCE_DIR / "external-gpu-pid-evidence.json")

    assert gpu["captured"] is True
    assert gpu["runtime_pid"] == runtime["runtime_pid"]
    assert gpu["capture_count"] >= 1
    assert gpu["max_gpu_memory_mib"] > 0
    assert gpu["min_gpu_memory_mib"] >= 0


def test_toto_license_review() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["model_id"] == MODEL_ID
    assert review["repo_id"] == REPO_ID
    assert review["revision"] == REVISION
    assert review["license"] == "Apache-2.0"
    assert review["review_status"] == "APPROVED"
    assert review["commercial_use"] is True
    assert review["personal_use"] is True


def test_toto_artifact_hashes() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    files = result["artifact"]["files"]

    assert files["README.md"]["sha256"] == (
        "c8f85b01eae1b586a742d9a0065df252bfe5855644f595969ca111bc206fcfcd"
    )

    assert files["config.json"]["sha256"] == (
        "7a926d130e401ab0c5fdb3564f46c8d917bd05c7b3ae26b9c22d2da2ef01d2d8"
    )

    assert files["model.safetensors"]["sha256"] == (
        "316660d5afb47943e531f39242e0b02ca0b8bb73be5709dfe07ca80dfce9805e"
    )

    assert files["model.safetensors"]["size_bytes"] == 16582848


def test_toto_runtime_status_ledger() -> None:
    status = _load_json(STATUS_PATH)

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert len(status["results"]) == 21
    assert status["total_models"] == 21
    assert status["runtime_certified_models"] == sum(
        item.get("runtime_status") == "CERTIFIED" for item in status["results"]
    )
    assert status["certified_models"] == sum(
        item.get("runtime_status") == "CERTIFIED" for item in status["results"]
    )
    assert status["blocked_models"] == sum(
        item.get("runtime_status") == "BLOCKED" for item in status["results"]
    )
    assert status["pending_models"] == sum(
        item.get("runtime_status") not in {"CERTIFIED", "BLOCKED"} for item in status["results"]
    )

    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_revision"] == REVISION
    assert row["runtime_code_revision"] == CODE_REVISION
    assert row["runtime_device"] == "cuda:0"
    assert row["runtime_output_device"] == "cuda:0"
    assert row["runtime_gpu_used"] is True
    assert row["runtime_cpu_fallback"] is False
    assert row["runtime_peak_vram_bytes"] > 0
    assert row["runtime_input_shape"] == [1, 7, 512]
    assert row["runtime_output_shape"] == [9, 1, 7, 1]
    assert row["runtime_model_parameter_count"] == (4144448)
    assert row["runtime_certification_scope"] == "FULL_INFERENCE"
    assert row["probabilistic_forecast_executed"] is True
    assert row["native_domain_contract_used"] is True
    assert row["lottery_domain_compatibility_certified"] is False
    assert row["forecast_accuracy_certified"] is False
    assert row["runtime_license_review"] == "APPROVED"
    assert row["commercial_use"] is True
    assert row["personal_use"] is True


def test_toto_docs_are_updated() -> None:
    docs = DOCS_PATH.read_text(encoding="utf-8")

    assert "### toto-2.0-4m" in docs
    assert "status: CERTIFIED" in docs
    assert "- Total models: 21" in docs
    assert "runtime certification scope: FULL_INFERENCE" in docs
    assert "probabilistic forecast executed: true" in docs
    assert "native domain contract used: true" in docs
    assert "lottery domain compatibility certified: false" in docs
    assert "forecast accuracy certified: false" in docs


def test_toto_sha256_manifest() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert entries

    for expected_digest, name in entries:
        path = EVIDENCE_DIR / name

        assert path.is_file(), name

        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()

        assert actual_digest == expected_digest
