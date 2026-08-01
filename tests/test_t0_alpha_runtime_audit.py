from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "t0-alpha"
BLOCKED_REASON = "GATED_ACCESS_REQUIRED"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_result_is_blocked() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["model_id"] == MODEL_ID
    assert result["runtime_status"] == "BLOCKED"
    assert result["runtime_vram_certified"] is False
    assert result["blocked_reason"] == BLOCKED_REASON
    assert result["snapshot_exists"] is True
    assert result["config_exists"] is False
    assert result["weight_files"] == []
    assert result["runtime_gpu_used"] is False
    assert result["runtime_cpu_fallback"] is False


def test_runtime_certification_is_blocked() -> None:
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert certification["runtime_status"] == "BLOCKED"
    assert certification["runtime_vram_certified"] is False
    assert certification["blocked_reason"] == BLOCKED_REASON
    assert certification["commercial_deployment_certified"] is False


def test_license_review() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["license"].lower() == "apache-2.0"
    assert review["commercial_use"] is True
    assert review["runtime_access_status"] == "GATED_ACCESS_REQUIRED"


def test_runtime_status_ledger_is_blocked() -> None:
    status = _load_json(STATUS_PATH)

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert status["total_models"] == 21
    assert status["runtime_certified_models"] == 19
    assert status["certified_models"] == 19
    assert status["blocked_models"] == 2
    assert status["pending_models"] == 0

    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_vram_certified"] is False
    assert row["runtime_blocked_reason"] == BLOCKED_REASON


def test_manifest_is_current() -> None:
    entries = (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()

    assert entries

    for entry in entries:
        expected, filename = entry.split("  ", 1)
        path = EVIDENCE_DIR / filename

        assert path.is_file(), filename

        actual = hashlib.sha256(path.read_bytes()).hexdigest()

        assert actual == expected
