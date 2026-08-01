from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_ID = "chronos-t5-base"
REPO_ID = "amazon/chronos-t5-base"
REVISION = "ad294eaacead15db499b740ea4122266dd2a81a2"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_chronos_t5_base_blocked_evidence_is_complete() -> None:
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


def test_chronos_t5_base_runtime_result_is_blocked() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")
    response = _load_json(EVIDENCE_DIR / "provider-response.json")
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert result["status"] == "BLOCKED"
    assert result["runtime_vram_certified"] is False
    assert result["model_id"] == MODEL_ID
    assert result["repo_id"] == REPO_ID
    assert result["revision"] == REVISION
    assert result["blocked_reason"]["code"] == "MODEL_WEIGHTS_MISSING"
    assert result["gpu_used"] is False
    assert result["cpu_fallback"] is False

    assert response["status"] == "MODEL_WEIGHTS_MISSING"
    assert response["blocker"]["missing_snapshot_path"].endswith(REVISION)

    assert certification["certification_status"] == "BLOCKED"
    assert certification["runtime_vram_certified"] is False


def test_chronos_t5_base_license_is_not_approved_without_snapshot() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["license"] == "apache-2.0"
    assert review["review_status"] == "BLOCKED"
    assert "unavailable" in review["limitations"][0]


def test_chronos_t5_base_runtime_status_ledger_is_blocked() -> None:
    status = _load_json(STATUS_PATH)

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert len(status["results"]) == 21
    assert status["runtime_certified_models"] == 8
    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_vram_certified"] is False
    assert row["runtime_revision"] == REVISION
    assert row["runtime_blocked_reason"] == "MODEL_WEIGHTS_MISSING"
    assert row["runtime_snapshot_path"].endswith(REVISION)
    assert row["runtime_resume_conditions"]


def test_chronos_t5_base_sha256_manifest_is_current() -> None:
    manifest = EVIDENCE_DIR / "sha256sum.txt"
    entries = [
        line.split("  ", 1) for line in manifest.read_text(encoding="utf-8").splitlines() if line
    ]

    assert len(entries) >= 14

    for expected_digest, name in entries:
        if name == "sha256sum.txt":
            continue

        actual_digest = hashlib.sha256((EVIDENCE_DIR / name).read_bytes()).hexdigest()

        assert actual_digest == expected_digest
