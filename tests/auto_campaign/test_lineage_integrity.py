from __future__ import annotations

import json
from pathlib import Path

from loto.auto_campaign.contracts import CampaignStage
from loto.auto_campaign.lineage_integrity import (
    evaluate_lineage_inputs,
    verify_lineage_artifacts,
    write_run_lineage,
)
from loto.auto_campaign.persistence import write_json, write_sha256s


def _coverage_run(tmp_path: Path) -> Path:
    root = tmp_path / "coverage"
    root.mkdir()
    write_json(
        root / "manifest.json",
        {
            "schema_version": "all-auto-api-coverage-v1",
            "status": "PASS",
            "coverage_state_status": "VERIFIED",
            "verification_status": "VERIFIED",
        },
    )
    write_json(root / "VERIFICATION_REPORT.json", {"status": "PASS"})
    write_sha256s(root)
    return root


def _new_run(root: Path, stage: CampaignStage) -> None:
    root.mkdir()
    write_json(root / "campaign_config.json", {"stage": stage.value, "seed": 1})
    write_json(root / "data_contract.json", {"status": "PASS", "rows": 100})
    write_json(
        root / "PROMOTION_GATE.json",
        {
            "schema_version": "all-auto-promotion-gate-v1",
            "status": "PASS",
            "target_stage": stage.value,
            "requires_gpu_runtime": False,
            "coverage_evidence": {"status": "PASS"},
            "runtime_evidence": None,
            "failures": [],
        },
    )
    gate = json.loads((root / "PROMOTION_GATE.json").read_text(encoding="utf-8"))
    write_json(
        root / "manifest.json",
        {
            "schema_version": "all-auto-campaign-run-v1",
            "status": "PASS",
            "stage": stage.value,
            "run_id": root.name,
            "code_sha256": "code-v1",
            "data_sha256": "data-v1",
            "promotion_gate_status": "PASS",
            "promotion_gate_path": "PROMOTION_GATE.json",
            "promotion_gate": gate,
        },
    )


def _mark_verified(root: Path) -> None:
    write_json(
        root / "VERIFICATION_REPORT.json",
        {
            "status": "PASS",
            "promotion_gate_verification": {"status": "PASS"},
            "lineage_verification": {"status": "PASS"},
            "failures": [],
        },
    )
    write_sha256s(root)


def _write_stage(
    root: Path,
    stage: CampaignStage,
    *,
    coverage: Path,
    source: Path | None = None,
    predecessor: Path | None = None,
) -> Path:
    _new_run(root, stage)
    result = write_run_lineage(
        run_root=root,
        target_stage=stage,
        source_run=source,
        predecessor_run=predecessor,
        coverage_run=coverage,
        runtime_run=None,
    )
    assert result["status"] == "PASS"
    assert result["lineage_status"] == "PASS"
    _mark_verified(root)
    return root


def _full_chain(tmp_path: Path) -> dict[str, Path]:
    coverage = _coverage_run(tmp_path)
    hpo = _write_stage(tmp_path / "hpo", CampaignStage.HPO, coverage=coverage)
    validation = _write_stage(
        tmp_path / "validation",
        CampaignStage.VALIDATE_TRIALS,
        coverage=coverage,
        source=hpo,
    )
    oof = _write_stage(
        tmp_path / "oof",
        CampaignStage.OOF,
        coverage=coverage,
        source=validation,
    )
    holdout = _write_stage(
        tmp_path / "holdout",
        CampaignStage.HOLDOUT,
        coverage=coverage,
        source=validation,
        predecessor=oof,
    )
    prospective = _write_stage(
        tmp_path / "prospective",
        CampaignStage.PROSPECTIVE,
        coverage=coverage,
        source=validation,
        predecessor=holdout,
    )
    return {
        "coverage": coverage,
        "hpo": hpo,
        "validation": validation,
        "oof": oof,
        "holdout": holdout,
        "prospective": prospective,
    }


def _manifest(root: Path) -> dict[str, object]:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def test_complete_hpo_to_prospective_chain_verifies(tmp_path: Path) -> None:
    chain = _full_chain(tmp_path)

    result = verify_lineage_artifacts(
        chain["prospective"],
        _manifest(chain["prospective"]),
    )

    assert result["status"] == "PASS"
    assert result["target_stage"] == "prospective"
    assert result["failures"] == []


def test_holdout_requires_verified_oof_predecessor(tmp_path: Path) -> None:
    coverage = _coverage_run(tmp_path)
    hpo = _write_stage(tmp_path / "hpo", CampaignStage.HPO, coverage=coverage)
    validation = _write_stage(
        tmp_path / "validation",
        CampaignStage.VALIDATE_TRIALS,
        coverage=coverage,
        source=hpo,
    )

    result = evaluate_lineage_inputs(
        target_stage=CampaignStage.HOLDOUT,
        source_run=validation,
        predecessor_run=None,
    )

    assert result["status"] == "BLOCKED"
    assert any("requires predecessor stage=oof" in failure for failure in result["failures"])


def test_predecessor_manifest_change_is_detected_even_after_rehash(tmp_path: Path) -> None:
    chain = _full_chain(tmp_path)
    holdout_manifest = _manifest(chain["holdout"])
    holdout_manifest["data_sha256"] = "mutated-data"
    write_json(chain["holdout"] / "manifest.json", holdout_manifest)
    write_sha256s(chain["holdout"])

    result = verify_lineage_artifacts(
        chain["prospective"],
        _manifest(chain["prospective"]),
    )

    assert result["status"] == "FAIL"
    assert any("predecessor run manifest SHA256 mismatch" in item for item in result["failures"])
    assert any("predecessor run SHA256SUMS SHA256 mismatch" in item for item in result["failures"])


def test_run_configuration_change_is_detected_after_root_rehash(tmp_path: Path) -> None:
    chain = _full_chain(tmp_path)
    config_path = chain["prospective"] / "campaign_config.json"
    write_json(config_path, {"stage": "prospective", "seed": 999})
    write_sha256s(chain["prospective"])

    result = verify_lineage_artifacts(
        chain["prospective"],
        _manifest(chain["prospective"]),
    )

    assert result["status"] == "FAIL"
    assert any("campaign config SHA256 mismatch" in item for item in result["failures"])


def test_promotion_gate_change_is_detected_after_root_rehash(tmp_path: Path) -> None:
    chain = _full_chain(tmp_path)
    gate_path = chain["prospective"] / "PROMOTION_GATE.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["status"] = "BLOCKED"
    write_json(gate_path, gate)
    write_sha256s(chain["prospective"])

    result = verify_lineage_artifacts(
        chain["prospective"],
        _manifest(chain["prospective"]),
    )

    assert result["status"] == "FAIL"
    assert any("promotion gate SHA256 mismatch" in item for item in result["failures"])


def test_wrong_predecessor_stage_is_blocked(tmp_path: Path) -> None:
    chain = _full_chain(tmp_path)

    result = evaluate_lineage_inputs(
        target_stage=CampaignStage.PROSPECTIVE,
        source_run=chain["validation"],
        predecessor_run=chain["oof"],
    )

    assert result["status"] == "BLOCKED"
    assert any(
        "predecessor run stage mismatch: expected=holdout, actual=oof" in failure
        for failure in result["failures"]
    )
