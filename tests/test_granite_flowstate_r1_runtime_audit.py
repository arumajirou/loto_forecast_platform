from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_ID = "granite-flowstate-r1"
REPO_ID = "ibm-granite/granite-timeseries-flowstate-r1"
REVISION = "05effc6cb39ee16dce9dd0064ed1a76e4b8ff464"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_granite_flowstate_blocked_evidence_is_complete() -> None:
    required = {
        "environment.txt",
        "python-environment.json",
        "provider-request.json",
        "provider-response.json",
        "runtime-result.json",
        "runtime-command.log",
        "nvidia-before.csv",
        "nvidia-after.csv",
        "nvidia-gpu-samples.csv",
        "nvidia-process-samples.csv",
        "nvidia-gpu-monitor.err",
        "nvidia-process-monitor.err",
        "license-review.json",
        "runtime-certification.json",
        "sha256sum.txt",
    }

    assert required.issubset({path.name for path in EVIDENCE_DIR.iterdir()})


def test_granite_flowstate_runtime_result_is_blocked() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    response = _load_json(EVIDENCE_DIR / "provider-response.json")
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert result["status"] == "BLOCKED"
    assert result["runtime_vram_certified"] is False
    assert result["model_id"] == MODEL_ID
    assert result["repo_id"] == REPO_ID
    assert result["revision"] == REVISION
    assert result["blocked_reason"]["code"] == "FIXED_SNAPSHOT_MISSING"
    assert result["gpu_used"] is False
    assert result["cpu_fallback"] is False

    assert response["status"] == "FIXED_SNAPSHOT_MISSING"
    assert response["blocker"]["missing_snapshot_path"].endswith(REVISION)
    assert response["blocker"]["candidate_loose_model_files_present"] is True

    assert certification["certification_status"] == "BLOCKED"
    assert certification["runtime_vram_certified"] is False


def test_granite_flowstate_license_is_not_approved_without_snapshot() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["license"] == "apache-2.0"
    assert review["review_status"] == "BLOCKED"
    assert "Pinned snapshot" in review["limitations"][0]


def test_granite_flowstate_runtime_status_ledger_is_blocked() -> None:
    status = _load_json(STATUS_PATH)

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert len(status["results"]) == 21
    assert status["runtime_certified_models"] == sum(
        item.get("runtime_status") == "CERTIFIED" for item in status["results"]
    )
    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_vram_certified"] is False
    assert row["runtime_revision"] == REVISION
    assert row["runtime_blocked_reason"] == "FIXED_SNAPSHOT_MISSING"
    assert row["runtime_snapshot_path"].endswith(REVISION)
    assert row["runtime_candidate_loose_model_path"].endswith(
        "ibm-granite__granite-timeseries-flowstate-r1"
    )
    assert row["runtime_resume_conditions"]


def test_granite_flowstate_sha256_manifest_is_current() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(entries) >= 14

    for expected_digest, name in entries:
        actual_digest = hashlib.sha256((EVIDENCE_DIR / name).read_bytes()).hexdigest()

        assert actual_digest == expected_digest
