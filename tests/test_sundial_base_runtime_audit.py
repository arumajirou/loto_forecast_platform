from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "sundial-base"
REPO_ID = "thuml/sundial-base-128m"
REVISION = "3212e42564493f520593e5414af4367fc4b49226"
WEIGHT_SHA256 = "414435b508391f92afadd2aaeec418c806776aeccbce12e638d73a139ca5ca78"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"
DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_probe_records_remote_code_block() -> None:
    probe = _load_json(EVIDENCE_DIR / "snapshot-probe.json")

    assert probe["repo_id"] == REPO_ID
    assert probe["revision"] == REVISION
    assert probe["snapshot_exists"] is True
    assert probe["result"] == "TRUST_REMOTE_CODE_REVIEW_REQUIRED"
    assert probe["trust_remote_code_required"] is True
    assert probe["weight_sha256"] == WEIGHT_SHA256


def test_runtime_is_blocked() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert result["status"] == "BLOCKED"
    assert result["blocked_reason"] == "TRUST_REMOTE_CODE_REVIEW_REQUIRED"
    assert result["runtime_vram_certified"] is False
    assert certification["certification_status"] == "BLOCKED"


def test_license_is_approved() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["license"] == "apache-2.0"
    assert review["review_status"] == "APPROVED"


def test_ledger_and_docs() -> None:
    status = _load_json(STATUS_PATH)
    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert len(status["results"]) == 21
    assert status["runtime_certified_models"] == 8
    assert status["blocked_models"] == 9
    assert status["pending_models"] == 4
    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_blocked_reason"] == "TRUST_REMOTE_CODE_REVIEW_REQUIRED"

    docs = DOCS_PATH.read_text(encoding="utf-8")
    assert "### sundial-base" in docs
    assert "Next model: t0-alpha" in docs
    assert "Blocked: 9" in docs


def test_sha256_manifest_is_current() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(entries) >= 8

    for expected, name in entries:
        assert hashlib.sha256((EVIDENCE_DIR / name).read_bytes()).hexdigest() == expected
