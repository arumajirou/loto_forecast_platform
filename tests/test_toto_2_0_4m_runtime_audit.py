from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "toto-2.0-4m"
REPO_ID = "Datadog/Toto-2.0-4m"
REVISION = "8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9"
BLOCKED_REASON = "RUNTIME_DEPENDENCY_MISSING"
EXPECTED_BLOCKED = 12
EXPECTED_PENDING = 1
EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"
DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_snapshot_probe_records_blocker() -> None:
    probe = _load_json(EVIDENCE_DIR / "snapshot-probe.json")

    assert probe["repo_id"] == REPO_ID
    assert probe["revision"] == REVISION
    assert probe["result"] == BLOCKED_REASON
    assert probe["snapshot_revision_matches"] is probe["snapshot_exists"]


def test_runtime_and_certification_are_blocked() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    cert = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert result["status"] == "BLOCKED"
    assert result["runtime_vram_certified"] is False
    assert result["blocked_reason"] == BLOCKED_REASON
    assert result["gpu_used"] is False
    assert result["cpu_fallback"] is False
    assert cert["certification_status"] == "BLOCKED"


def test_license_review_status() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["license"] == "apache-2.0"
    assert review["review_status"] == "APPROVED"


def test_runtime_status_ledger_and_docs_are_updated() -> None:
    status = _load_json(STATUS_PATH)
    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert len(status["results"]) == 21
    assert status["runtime_certified_models"] == sum(
        item.get("runtime_status") == "CERTIFIED" for item in status["results"]
    )
    assert status["blocked_models"] == sum(
        item.get("runtime_status") == "BLOCKED" for item in status["results"]
    )
    assert status["pending_models"] == sum(
        item.get("runtime_status") not in {"CERTIFIED", "BLOCKED"} for item in status["results"]
    )
    assert row["repo_id"] == REPO_ID
    assert row["revision"] == REVISION
    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_blocked_reason"] == BLOCKED_REASON

    docs = DOCS_PATH.read_text(encoding="utf-8")
    assert f"### {MODEL_ID}" in docs
    assert f"blocked reason: {BLOCKED_REASON}" in docs
    assert "Blocked:" in docs
    assert "Pending:" in docs
    assert "Next model:" in docs


def test_sha256_manifest_is_current() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(entries) >= 8

    for expected, name in entries:
        assert hashlib.sha256((EVIDENCE_DIR / name).read_bytes()).hexdigest() == expected
