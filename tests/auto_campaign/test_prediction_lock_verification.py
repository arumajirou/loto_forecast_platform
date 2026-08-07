from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import coverage_verification
from loto.auto_campaign import lineage_verification as verification
from loto.auto_campaign.persistence import sha256_file, write_json
from loto.auto_campaign.verification_seal import write_verification_seal


def _manifest() -> dict[str, Any]:
    return {
        "status": "PASS",
        "stage": "prospective",
        "promotion_gate_status": "PASS",
        "promotion_gate_path": "PROMOTION_GATE.json",
        "promotion_gate": {"status": "PASS"},
        "lineage_status": "PASS",
        "lineage_path": "LINEAGE.json",
    }


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    prediction_result: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        coverage_verification,
        "verify_run_with_coverage",
        lambda _root: {"status": "PASS", "failures": []},
    )
    monkeypatch.setattr(
        verification,
        "verify_promotion_gate_artifacts",
        lambda _root, _manifest_payload: {
            "status": "PASS",
            "failures": [],
        },
    )
    monkeypatch.setattr(
        verification,
        "verify_lineage_artifacts",
        lambda _root, _manifest_payload: {
            "status": "PASS",
            "failures": [],
        },
    )
    monkeypatch.setattr(
        verification,
        "verify_lineage_semantics",
        lambda _root, _manifest_payload: {
            "status": "PASS",
            "target_stage": "prospective",
            "failures": [],
        },
    )
    monkeypatch.setattr(
        verification,
        "verify_prediction_lock",
        lambda _root, _manifest_payload: prediction_result,
    )


def test_missing_prediction_lock_fails_before_sealing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "manifest.json", _manifest())
    _patch_common(
        monkeypatch,
        {
            "status": "FAIL",
            "task_count": 0,
            "failures": ["prediction lock missing"],
        },
    )
    sealed = False

    def fake_seal(_root: Path, _result: dict[str, Any]) -> None:
        nonlocal sealed
        sealed = True
        return None

    monkeypatch.setattr(verification, "write_verification_seal", fake_seal)

    result = verification.verify_run_with_lineage(tmp_path)

    assert result["status"] == "FAIL"
    assert result["prediction_lock_verification"]["status"] == "FAIL"
    assert any("prediction-lock:prediction lock missing" in item for item in result["failures"])
    assert sealed is False


def test_prediction_lock_pass_is_embedded_in_final_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "manifest.json", _manifest())
    prediction_result = {
        "status": "PASS",
        "task_count": 36,
        "locked_at": "2026-08-05T07:00:00+00:00",
        "failures": [],
    }
    _patch_common(monkeypatch, prediction_result)
    monkeypatch.setattr(
        verification,
        "write_verification_seal",
        lambda _root, _result: {"status": "PASS"},
    )
    monkeypatch.setattr(
        verification,
        "verify_verification_seal",
        lambda _root: {"status": "PASS", "failures": []},
    )

    result = verification.verify_run_with_lineage(tmp_path)

    assert result["status"] == "PASS"
    report = json.loads(
        (tmp_path / "VERIFICATION_REPORT.json").read_text(encoding="utf-8")
    )
    assert report["prediction_lock_verification"]["status"] == "PASS"
    assert report["prediction_lock_verification"]["task_count"] == 36


def test_verification_seal_binds_prediction_lock_hash(tmp_path: Path) -> None:
    write_json(tmp_path / "manifest.json", {"status": "PASS", "stage": "prospective"})
    write_json(tmp_path / "PREDICTION_LOCK.json", {"status": "LOCKED", "tasks": [1]})
    result = {
        "status": "PASS",
        "run_manifest_status": "PASS",
        "coverage_state_verification": {"status": "NOT_APPLICABLE"},
        "promotion_gate_verification": {"status": "PASS"},
        "lineage_verification": {"status": "PASS"},
        "prediction_lock_verification": {"status": "PASS"},
        "failures": [],
    }

    payload = write_verification_seal(tmp_path, result)

    assert payload is not None
    assert payload["prediction_lock_sha256"] == sha256_file(
        tmp_path / "PREDICTION_LOCK.json"
    )
    assert payload["components"]["prediction_lock_status"] == "PASS"
