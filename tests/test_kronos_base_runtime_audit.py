from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_ID = "kronos-base"
REPO_ID = "NeoQuasar/Kronos-base"
REVISION = "2b554741eca47781b64468546e77fef3e85130e6"

TOKENIZER_REPO_ID = "NeoQuasar/Kronos-Tokenizer-base"
TOKENIZER_REVISION = "0e0117387f39004a9016484a186a908917e22426"

CODE_REVISION = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID

STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"

DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_kronos_base_runtime_result_passed() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["status"] == "PASS"
    assert result["model_id"] == MODEL_ID
    assert result["repo_id"] == REPO_ID
    assert result["revision"] == REVISION

    assert result["tokenizer_repo_id"] == TOKENIZER_REPO_ID
    assert result["tokenizer_revision"] == TOKENIZER_REVISION
    assert result["kronos_code_revision"] == CODE_REVISION

    assert result["prediction_shape"] == [4, 6]
    assert result["prediction_columns"] == [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]
    assert len(result["prediction_records"]) == 4
    assert result["output_finite"] is True


def test_kronos_base_classes_and_parameters() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["model_class"] == "Kronos"
    assert result["tokenizer_class"] == "KronosTokenizer"
    assert result["predictor_class"] == "KronosPredictor"

    assert result["model_parameter_count"] == 102310592
    assert result["tokenizer_parameter_count"] == 3958042

    assert result["lookback"] == 128
    assert result["prediction_length"] == 4
    assert result["max_context"] == 512
    assert result["native_domain"] == ("financial_ohlcv_kline")


def test_kronos_base_cuda_evidence() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["model_device"] == "cuda:0"
    assert result["tokenizer_device"] == "cuda:0"
    assert result["runtime_gpu_used"] is True
    assert result["runtime_cpu_fallback"] is False
    assert result["peak_vram_bytes"] > 0


def test_kronos_base_full_inference_scope() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["runtime_certification_scope"] == "FULL_INFERENCE"
    assert result["tokenizer_executed"] is True
    assert result["autoregressive_forecast_executed"] is True
    assert result["native_domain_contract_used"] is True
    assert result["lottery_domain_compatibility_certified"] is False
    assert result["forecast_accuracy_certified"] is False


def test_kronos_base_runtime_certification() -> None:
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert certification["runtime_status"] == "CERTIFIED"
    assert certification["runtime_vram_certified"] is True
    assert certification["runtime_gpu_used"] is True
    assert certification["runtime_cpu_fallback"] is False
    assert certification["runtime_certification_scope"] == "FULL_INFERENCE"
    assert certification["tokenizer_executed"] is True
    assert certification["autoregressive_forecast_executed"] is True
    assert certification["native_domain_contract_used"] is True
    assert certification["lottery_domain_compatibility_certified"] is False
    assert certification["forecast_accuracy_certified"] is False
    assert all(certification["checks"].values())


def test_kronos_base_external_gpu_pid() -> None:
    runtime = _load_json(EVIDENCE_DIR / "runtime-result.json")

    gpu = _load_json(EVIDENCE_DIR / "external-gpu-pid-evidence.json")

    assert gpu["captured"] is True
    assert gpu["runtime_pid"] == runtime["runtime_pid"]
    assert gpu["capture_count"] >= 1
    assert gpu["max_gpu_memory_mib"] > 0
    assert gpu["min_gpu_memory_mib"] >= 0


def test_kronos_base_license_review() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["model_id"] == MODEL_ID
    assert review["repo_id"] == REPO_ID
    assert review["revision"] == REVISION
    assert review["license"].lower() == "mit"
    assert review["review_status"] == "APPROVED"
    assert review["commercial_use"] is True


def test_kronos_base_model_hashes() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    files = result["model_artifact"]["files"]

    assert files["config.json"]["sha256"] == (
        "77ebc3038b647709b92be002f801d72e1a385f4c8c2c5aa1cc6cf21fcfe44eb2"
    )

    assert files["model.safetensors"]["sha256"] == (
        "abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83"
    )

    assert files["model.safetensors"]["size_bytes"] == 409264008


def test_kronos_base_tokenizer_hashes() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    files = result["tokenizer_artifact"]["files"]

    assert files["config.json"]["sha256"] == (
        "2366e7ccfec76cbc19cf3c4c1b9c5d901be336ca1e83f2d2292c9bff381b77a2"
    )

    assert files["model.safetensors"]["sha256"] == (
        "59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee"
    )

    assert files["model.safetensors"]["size_bytes"] == 15842368


def test_kronos_base_runtime_status_ledger() -> None:
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
    assert row["runtime_tokenizer_repo_id"] == TOKENIZER_REPO_ID
    assert row["runtime_tokenizer_revision"] == TOKENIZER_REVISION
    assert row["runtime_code_revision"] == CODE_REVISION
    assert row["runtime_device"] == "cuda:0"
    assert row["runtime_tokenizer_device"] == "cuda:0"
    assert row["runtime_gpu_used"] is True
    assert row["runtime_cpu_fallback"] is False
    assert row["runtime_peak_vram_bytes"] > 0
    assert row["runtime_certification_scope"] == "FULL_INFERENCE"
    assert row["tokenizer_executed"] is True
    assert row["autoregressive_forecast_executed"] is True
    assert row["native_domain_contract_used"] is True
    assert row["lottery_domain_compatibility_certified"] is False
    assert row["forecast_accuracy_certified"] is False
    assert row["runtime_license_review"] == "APPROVED"


def test_kronos_base_docs_are_updated() -> None:
    docs = DOCS_PATH.read_text(encoding="utf-8")

    assert "### kronos-base" in docs
    assert "status: CERTIFIED" in docs
    assert "- Total models: 21" in docs
    assert "runtime certification scope: FULL_INFERENCE" in docs
    assert "native domain: financial OHLCV / K-line" in docs
    assert "tokenizer executed: true" in docs
    assert "autoregressive forecast executed: true" in docs
    assert "lottery domain compatibility certified: false" in docs
    assert "forecast accuracy certified: false" in docs


def test_kronos_base_sha256_manifest() -> None:
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
