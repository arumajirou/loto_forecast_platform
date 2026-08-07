from __future__ import annotations

import json
from pathlib import Path

from loto.auto_campaign.persistence import sha256_file, write_json
from loto.auto_campaign.verification_seal import write_verification_seal


def test_legacy_nonprospective_seal_is_not_rewritten(tmp_path: Path) -> None:
    write_json(tmp_path / "manifest.json", {"status": "PASS", "stage": "holdout"})
    result = {
        "status": "PASS",
        "run_manifest_status": "PASS",
        "coverage_state_verification": {"status": "NOT_APPLICABLE"},
        "promotion_gate_verification": {"status": "PASS"},
        "lineage_verification": {"status": "PASS"},
        "prediction_lock_verification": {"status": "NOT_APPLICABLE"},
        "failures": [],
    }
    current = write_verification_seal(tmp_path, result)
    assert current is not None

    legacy = dict(current)
    legacy.pop("prediction_lock_sha256", None)
    components = dict(legacy["components"])
    components.pop("prediction_lock_status", None)
    legacy["components"] = components
    write_json(tmp_path / "VERIFICATION_SEAL.json", legacy)
    before = (tmp_path / "VERIFICATION_SEAL.json").read_bytes()
    before_sha = sha256_file(tmp_path / "VERIFICATION_SEAL.json")

    returned = write_verification_seal(tmp_path, result)

    assert returned == legacy
    assert (tmp_path / "VERIFICATION_SEAL.json").read_bytes() == before
    assert sha256_file(tmp_path / "VERIFICATION_SEAL.json") == before_sha
    assert json.loads(before.decode("utf-8"))["sealed_at"] == current["sealed_at"]
