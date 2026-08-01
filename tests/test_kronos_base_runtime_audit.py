from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_ID = "kronos-base"
REPO_ID = "NeoQuasar/Kronos-base"
REVISION = "2b554741eca47781b64468546e77fef3e85130e6"
BLOCKED_REASON = "PARTIAL_SNAPSHOT"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"
DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_kronos_base_snapshot_probe_records_partial_snapshot() -> None:
    probe = _load_json(EVIDENCE_DIR / "snapshot-probe.json")

    assert probe["model_id"] == MODEL_ID
    assert probe["repo_id"] == REPO_ID
    assert probe["revision"] == REVISION
    assert probe["snapshot_exists"] is True
    assert probe["snapshot_revision_matches"] is True
    assert probe["result"] == BLOCKED_REASON
    assert probe["missing_files"] == ["config.json", "model.safetensors"]
    assert probe["existing_files"][0]["name"] == "README.md"
    assert probe["existing_files"][0]["is_symlink"] is True


def test_kronos_base_runtime_result_is_blocked() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")
    blocked = _load_json(EVIDENCE_DIR / "blocked-reason.json")

    assert result["status"] == "BLOCKED"
    assert result["runtime_vram_certified"] is False
    assert result["model_id"] == MODEL_ID
    assert result["repo_id"] == REPO_ID
    assert result["revision"] == REVISION
    assert result["blocked_reason"] == BLOCKED_REASON
    assert result["retry_condition"]
    assert result["gpu_used"] is False
    assert result["cpu_fallback"] is False
    assert result["peak_vram_bytes"] is None

    assert certification["certification_status"] == "BLOCKED"
    assert certification["runtime_vram_certified"] is False
    assert certification["blocked_reason"] == BLOCKED_REASON
    assert certification["retry_condition"] == result["retry_condition"]

    assert blocked["blocked_reason"] == BLOCKED_REASON
    assert "Missing files: config.json, model.safetensors" in blocked["facts"]


def test_kronos_base_license_review_is_approved_from_snapshot_readme() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["model_id"] == MODEL_ID
    assert review["repo_id"] == REPO_ID
    assert review["revision"] == REVISION
    assert review["license"] == "mit"
    assert review["review_status"] == "APPROVED"
    assert review["commercial_use"] is True
    assert review["redistribution_allowed"] is True
    assert review["notice_required_on_distribution"] is True


def test_kronos_base_runtime_status_ledger_is_blocked() -> None:
    status = _load_json(STATUS_PATH)

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert len(status["results"]) == 21
    assert status["total_models"] == len(status["results"])
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

    assert row["repo_id"] == REPO_ID
    assert row["revision"] == REVISION
    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_vram_certified"] is False
    assert row["runtime_revision"] == REVISION
    assert row["runtime_blocked_reason"] == BLOCKED_REASON
    assert row["runtime_missing_files"] == ["config.json", "model.safetensors"]
    assert row["retry_condition"]
    assert row["runtime_license_review"] == "APPROVED"


def test_kronos_base_docs_are_updated() -> None:
    docs = DOCS_PATH.read_text(encoding="utf-8")

    assert "### kronos-base" in docs
    assert "blocked reason: PARTIAL_SNAPSHOT" in docs
    assert "Next model:" in docs
    assert "Blocked:" in docs
    assert "Pending:" in docs


def test_kronos_base_sha256_manifest_is_current() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(entries) >= 8

    for expected_digest, name in entries:
        actual_digest = hashlib.sha256((EVIDENCE_DIR / name).read_bytes()).hexdigest()

        assert actual_digest == expected_digest
