from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_ID = "moirai-2.0-small"
REPO_ID = "Salesforce/moirai-2.0-R-small"
REVISION = "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"
BLOCKED_REASON = "LICENSE_REVIEW_REQUIRED"
WEIGHT_SHA256 = "fb5652a3db8ea572606221b7cb1e77bb8962b168e4d4cc752cf31ceb04074669"
CONFIG_SHA256 = "6b74b03c8ec199fabc352c0203465958142ca468183da68549652734836f853d"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"
DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_moirai_2_0_small_snapshot_probe_records_complete_snapshot_and_license_block() -> None:
    probe = _load_json(EVIDENCE_DIR / "snapshot-probe.json")

    assert probe["model_id"] == MODEL_ID
    assert probe["repo_id"] == REPO_ID
    assert probe["revision"] == REVISION
    assert probe["snapshot_exists"] is True
    assert probe["snapshot_revision_matches"] is True
    assert probe["result"] == BLOCKED_REASON
    assert probe["weight_candidates"] == ["model.safetensors"]
    assert probe["missing_files"] == []
    assert probe["weight_sha256"] == WEIGHT_SHA256
    assert probe["config_sha256"] == CONFIG_SHA256


def test_moirai_2_0_small_runtime_result_is_blocked() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert result["status"] == "BLOCKED"
    assert result["runtime_vram_certified"] is False
    assert result["blocked_reason"] == BLOCKED_REASON
    assert result["gpu_used"] is False
    assert result["cpu_fallback"] is False
    assert result["weight_sha256"] == WEIGHT_SHA256
    assert result["config_sha256"] == CONFIG_SHA256

    assert certification["certification_status"] == "BLOCKED"
    assert certification["license_review_status"] == "REJECTED"
    assert certification["blocked_reason"] == BLOCKED_REASON


def test_moirai_2_0_small_license_review_is_rejected() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["license"] == "cc-by-nc-4.0"
    assert review["review_status"] == "REJECTED"
    assert review["commercial_use"] is False


def test_moirai_2_0_small_runtime_status_ledger_is_blocked() -> None:
    status = _load_json(STATUS_PATH)
    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert len(status["results"]) == 21
    assert status["runtime_certified_models"] == 8
    assert status["blocked_models"] == 6
    assert status["pending_models"] == 7
    assert row["repo_id"] == REPO_ID
    assert row["revision"] == REVISION
    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_blocked_reason"] == BLOCKED_REASON
    assert row["runtime_license_review"] == "REJECTED"
    assert row["runtime_weight_sha256"] == WEIGHT_SHA256
    assert row["runtime_config_sha256"] == CONFIG_SHA256


def test_moirai_2_0_small_docs_are_updated() -> None:
    docs = DOCS_PATH.read_text(encoding="utf-8")

    assert "### moirai-2.0-small" in docs
    assert "blocked reason: LICENSE_REVIEW_REQUIRED" in docs
    assert "Next model: moment-1-large" in docs
    assert "Blocked: 6" in docs
    assert "Pending: 7" in docs


def test_moirai_2_0_small_sha256_manifest_is_current() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(entries) >= 8
    for expected_digest, name in entries:
        actual_digest = hashlib.sha256((EVIDENCE_DIR / name).read_bytes()).hexdigest()
        assert actual_digest == expected_digest
