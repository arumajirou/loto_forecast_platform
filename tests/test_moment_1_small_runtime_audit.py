from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "moment-1-small"
REPO_ID = "AutonLab/MOMENT-1-small"
REVISION = "411e288267f82cce86296dbe4d6c8bc533cc162f"
EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"
DOCS_PATH = ROOT / "docs" / "tsfm-runtime-certification-progress.md"


def _j(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_probe() -> None:
    p = _j(EVIDENCE_DIR / "snapshot-probe.json")
    assert p["repo_id"] == REPO_ID
    assert p["revision"] == REVISION
    assert p["repo_cache_exists"] is False
    assert p["snapshot_exists"] is False
    assert p["result"] == "FIXED_SNAPSHOT_MISSING"


def test_runtime_blocked() -> None:
    r = _j(EVIDENCE_DIR / "runtime-result.json")
    c = _j(EVIDENCE_DIR / "runtime-certification.json")
    assert r["status"] == "BLOCKED"
    assert r["runtime_vram_certified"] is False
    assert r["blocked_reason"] == "FIXED_SNAPSHOT_MISSING"
    assert r["retry_condition"]
    assert c["certification_status"] == "BLOCKED"


def test_license_blocked() -> None:
    review = _j(EVIDENCE_DIR / "license-review.json")
    assert review["license"] == "mit"
    assert review["review_status"] == "BLOCKED"


def test_ledger_docs() -> None:
    s = _j(STATUS_PATH)
    row = next(x for x in s["results"] if x["model_id"] == MODEL_ID)
    assert len(s["results"]) == 21
    assert s["runtime_certified_models"] == 8
    assert s["blocked_models"] == 8
    assert s["pending_models"] == 5
    assert row["runtime_status"] == "BLOCKED"
    assert row["runtime_blocked_reason"] == "FIXED_SNAPSHOT_MISSING"
    d = DOCS_PATH.read_text(encoding="utf-8")
    assert "### moment-1-small" in d
    assert "Next model: sundial-base" in d
    assert "Blocked: 8" in d


def test_sha256() -> None:
    entries = [
        line.split("  ", 1)
        for line in (EVIDENCE_DIR / "sha256sum.txt").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(entries) >= 8
    for h, n in entries:
        assert hashlib.sha256((EVIDENCE_DIR / n).read_bytes()).hexdigest() == h
