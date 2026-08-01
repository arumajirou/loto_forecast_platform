from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "moment-1-large"
REPO_ID = "AutonLab/MOMENT-1-large"
REVISION = "ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc"
EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"
DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_snapshot_probe_records_partial_snapshot() -> None:
    probe = _load_json(EVIDENCE_DIR / "snapshot-probe.json")
    assert probe["repo_id"] == REPO_ID
    assert probe["revision"] == REVISION
    assert probe["snapshot_exists"] is True
    assert probe["snapshot_revision_matches"] is True
    assert probe["result"] == "PARTIAL_SNAPSHOT"
    assert "config.json" in probe["missing_files"]
    assert probe["existing_files"][0]["name"] == "README.md"


def test_runtime_and_certification_are_blocked() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    cert = _load_json(EVIDENCE_DIR / "runtime-certification.json")
    assert result["status"] == "BLOCKED"
    assert result["runtime_vram_certified"] is False
    assert result["blocked_reason"] == "PARTIAL_SNAPSHOT"
    assert result["retry_condition"]
    assert result["gpu_used"] is False
    assert result["cpu_fallback"] is False
    assert cert["certification_status"] == "BLOCKED"
    assert cert["license_review_status"] == "APPROVED"


def test_license_review_is_approved() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")
    assert review["license"] == "mit"
    assert review["review_status"] == "APPROVED"
    assert review["commercial_use"] is True


def test_runtime_status_ledger_is_blocked() -> None:
    status = _load_json(STATUS_PATH)
    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)
    assert len(status["results"]) == 21
    assert status["runtime_certified_models"] == 8
    assert status["blocked_models"] == 7
    assert status["pending_models"] == 6
    assert row["repo_id"] == REPO_ID
    assert row["revision"] == REVISION
    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_blocked_reason"] == "PARTIAL_SNAPSHOT"
    assert row["runtime_license_review"] == "APPROVED"


def test_docs_are_updated() -> None:
    docs = DOCS_PATH.read_text(encoding="utf-8")
    assert "### moment-1-large" in docs
    assert "blocked reason: PARTIAL_SNAPSHOT" in docs
    assert "Next model: moment-1-small" in docs
    assert "Blocked: 7" in docs
    assert "Pending: 6" in docs


def test_sha256_manifest_is_current() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(entries) >= 8
    for expected, name in entries:
        assert hashlib.sha256((EVIDENCE_DIR / name).read_bytes()).hexdigest() == expected
