from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_ID = "moirai-2.0-small"
REPO_ID = "Salesforce/moirai-2.0-R-small"
REVISION = "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"
WEIGHT_SHA256 = "fb5652a3db8ea572606221b7cb1e77bb8962b168e4d4cc752cf31ceb04074669"
CONFIG_SHA256 = "6b74b03c8ec199fabc352c0203465958142ca468183da68549652734836f853d"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"
DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_result_passed() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["status"] == "PASS"
    assert result["model_id"] == MODEL_ID
    assert result["repo_id"] == REPO_ID
    assert result["revision"] == REVISION
    assert result["prediction_shape"] == [7]
    assert result["output_finite"] is True
    assert len(result["predictions"]) == 7


def test_model_and_forecast_properties() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["model_class"] == "Moirai2Module"
    assert result["forecast_class"] == "Moirai2Forecast"
    assert result["model_parameter_count"] == 11387208
    assert result["context_length"] == 128
    assert result["prediction_length"] == 1
    assert result["target_dim"] == 7
    assert result["quantile_support"] is True
    assert result["quantile_shape"] == [1, 7]


def test_cuda_runtime_evidence() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["model_device"] == "cuda:0"
    assert result["runtime_gpu_used"] is True
    assert result["runtime_cpu_fallback"] is False
    assert result["peak_vram_bytes"] > 0


def test_certification_scope() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert result["runtime_certification_scope"] == "FULL_INFERENCE"
    assert result["native_forecast_contract_used"] is True
    assert result["lottery_domain_compatibility_certified"] is False
    assert result["forecast_accuracy_certified"] is False

    assert certification["runtime_status"] == "CERTIFIED"
    assert certification["runtime_vram_certified"] is True
    assert certification["runtime_certification_scope"] == "FULL_INFERENCE"
    assert certification["license_scope"] == "PERSONAL_NONCOMMERCIAL_ONLY"
    assert certification["commercial_deployment_certified"] is False
    assert all(certification["checks"].values())


def test_snapshot_hashes() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["snapshot_complete"] is True
    assert result["config_sha256"] == CONFIG_SHA256
    assert list(result["weight_sha256"].values()) == [WEIGHT_SHA256]


def test_runtime_environment() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    environment = result["runtime_environment"]

    assert environment["uni2ts_version"] == "2.0.0"
    assert environment["gluonts_version"] == "0.14.4"
    assert environment["torch_version"].startswith("2.13.0+cu130")


def test_external_gpu_pid_evidence() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    gpu = _load_json(EVIDENCE_DIR / "external-gpu-pid-evidence.json")

    assert gpu["captured"] is True
    assert gpu["runtime_pid"] == result["runtime_pid"]
    assert gpu["capture_count"] >= 1
    assert gpu["max_gpu_memory_mib"] > 0


def test_personal_noncommercial_license() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["license"] == "CC-BY-NC-4.0"
    assert review["license_review"] == "APPROVED_PERSONAL_NONCOMMERCIAL"
    assert review["personal_use"] is True
    assert review["personal_noncommercial_use"] is True
    assert review["commercial_use"] is False
    assert review["commercial_deployment_certified"] is False


def test_runtime_status_ledger() -> None:
    status = _load_json(STATUS_PATH)

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert len(status["results"]) == 21
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
    assert row["runtime_device"] == "cuda:0"
    assert row["runtime_gpu_used"] is True
    assert row["runtime_cpu_fallback"] is False
    assert row["runtime_peak_vram_bytes"] > 0
    assert row["runtime_prediction_shape"] == [7]
    assert row["runtime_model_parameter_count"] == 11387208
    assert row["runtime_certification_scope"] == "FULL_INFERENCE"
    assert row["license_scope"] == "PERSONAL_NONCOMMERCIAL_ONLY"
    assert row["commercial_use"] is False
    assert row["commercial_deployment_certified"] is False


def test_docs_updated() -> None:
    docs = DOCS_PATH.read_text(encoding="utf-8")

    assert "### moirai-2.0-small" in docs
    assert "status: CERTIFIED" in docs
    assert "runtime certification scope: FULL_INFERENCE" in docs
    assert "license scope: PERSONAL_NONCOMMERCIAL_ONLY" in docs
    assert "commercial deployment certified: false" in docs


def test_sha256_manifest() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert entries

    for expected_digest, name in entries:
        path = EVIDENCE_DIR / name
        assert path.is_file(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_digest
