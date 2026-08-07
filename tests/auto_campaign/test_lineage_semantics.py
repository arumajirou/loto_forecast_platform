from __future__ import annotations

from pathlib import Path

from loto.auto_campaign.lineage_verification import verify_lineage_semantics
from loto.auto_campaign.persistence import write_json


def _evidence(stage: str, path: str) -> dict[str, object]:
    return {
        "stage": stage,
        "path": path,
        "verification_status": "PASS",
    }


def test_lineage_on_ungated_stage_returns_failure_not_exception(tmp_path: Path) -> None:
    write_json(
        tmp_path / "LINEAGE.json",
        {
            "target_stage": "smoke",
            "run": {
                "manifest_code_sha256": "code",
                "manifest_data_sha256": "data",
            },
            "source_evidence": None,
            "predecessor_evidence": None,
            "coverage_evidence": {"verification_status": "PASS"},
            "runtime_evidence": None,
        },
    )
    write_json(
        tmp_path / "PROMOTION_GATE.json",
        {"requires_gpu_runtime": False},
    )

    result = verify_lineage_semantics(tmp_path, {"stage": "smoke"})

    assert result["status"] == "FAIL"
    assert any("not gated" in failure for failure in result["failures"])


def test_prospective_rejects_oof_as_immediate_predecessor(tmp_path: Path) -> None:
    write_json(
        tmp_path / "LINEAGE.json",
        {
            "target_stage": "prospective",
            "run": {
                "manifest_code_sha256": "code",
                "manifest_data_sha256": "data",
            },
            "source_evidence": _evidence("validate-trials", "/runs/validation"),
            "predecessor_evidence": _evidence("oof", "/runs/oof"),
            "coverage_evidence": {"verification_status": "PASS"},
            "runtime_evidence": None,
        },
    )
    write_json(
        tmp_path / "PROMOTION_GATE.json",
        {"requires_gpu_runtime": False},
    )

    result = verify_lineage_semantics(tmp_path, {"stage": "prospective"})

    assert result["status"] == "FAIL"
    assert any(
        "predecessor evidence stage mismatch: expected=holdout, actual=oof" in failure
        for failure in result["failures"]
    )


def test_hpo_rejects_source_evidence(tmp_path: Path) -> None:
    write_json(
        tmp_path / "LINEAGE.json",
        {
            "target_stage": "hpo",
            "run": {
                "manifest_code_sha256": "code",
                "manifest_data_sha256": "data",
            },
            "source_evidence": _evidence("validate-trials", "/runs/validation"),
            "predecessor_evidence": None,
            "coverage_evidence": {"verification_status": "PASS"},
            "runtime_evidence": None,
        },
    )
    write_json(
        tmp_path / "PROMOTION_GATE.json",
        {"requires_gpu_runtime": False},
    )

    result = verify_lineage_semantics(tmp_path, {"stage": "hpo"})

    assert result["status"] == "FAIL"
    assert any("source evidence must be absent" in failure for failure in result["failures"])
