from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import coverage_verification
from loto.auto_campaign import lineage_verification as verification
from loto.auto_campaign.persistence import write_json


def _gate(stage: str = "hpo") -> dict[str, Any]:
    return {
        "schema_version": "all-auto-promotion-gate-v1",
        "status": "PASS",
        "target_stage": stage,
        "requires_gpu_runtime": False,
        "coverage_evidence": {"status": "PASS"},
        "runtime_evidence": None,
        "failures": [],
    }


def _manifest(gate: dict[str, Any], stage: str = "hpo") -> dict[str, Any]:
    return {
        "schema_version": "all-auto-campaign-run-v1",
        "status": "PASS",
        "stage": stage,
        "promotion_gate_status": "PASS",
        "promotion_gate_path": "PROMOTION_GATE.json",
        "promotion_gate": gate,
    }


def test_promotion_gate_artifact_and_embedded_copy_verify(tmp_path: Path) -> None:
    gate = _gate()
    write_json(tmp_path / "PROMOTION_GATE.json", gate)

    result = verification.verify_promotion_gate_artifacts(
        tmp_path,
        _manifest(gate),
    )

    assert result["status"] == "PASS"
    assert result["target_stage"] == "hpo"
    assert result["failures"] == []


def test_embedded_gate_mismatch_fails(tmp_path: Path) -> None:
    gate = _gate()
    write_json(tmp_path / "PROMOTION_GATE.json", gate)
    manifest = _manifest({**gate, "target_stage": "oof"})

    result = verification.verify_promotion_gate_artifacts(tmp_path, manifest)

    assert result["status"] == "FAIL"
    assert any("differs from PROMOTION_GATE.json" in item for item in result["failures"])


def test_gated_run_without_lineage_fails_standard_verify(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gate = _gate()
    write_json(tmp_path / "PROMOTION_GATE.json", gate)
    write_json(tmp_path / "manifest.json", _manifest(gate))
    monkeypatch.setattr(
        coverage_verification,
        "verify_run_with_coverage",
        lambda _root: {"status": "PASS", "failures": []},
    )

    result = verification.verify_run_with_lineage(tmp_path)

    assert result["status"] == "FAIL"
    assert result["promotion_gate_verification"]["status"] == "PASS"
    assert result["lineage_verification"]["status"] == "FAIL"
    assert any("gated run is missing LINEAGE.json" in item for item in result["failures"])


def _patch_pass_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        coverage_verification,
        "verify_run_with_coverage",
        lambda _root: {
            "status": "PASS",
            "run_manifest_status": "PASS",
            "coverage_state_verification": {"status": "NOT_APPLICABLE"},
            "failures": [],
        },
    )
    monkeypatch.setattr(
        verification,
        "verify_promotion_gate_artifacts",
        lambda _root, _manifest_payload: {
            "applicable": True,
            "status": "PASS",
            "failures": [],
        },
    )
    monkeypatch.setattr(
        verification,
        "verify_lineage_artifacts",
        lambda _root, _manifest_payload: {
            "applicable": True,
            "status": "PASS",
            "target_stage": "hpo",
            "chain_sha256": "abc",
            "failures": [],
        },
    )
    monkeypatch.setattr(
        verification,
        "verify_lineage_semantics",
        lambda _root, _manifest_payload: {
            "status": "PASS",
            "target_stage": "hpo",
            "failures": [],
        },
    )


def test_standard_report_embeds_promotion_lineage_and_seal_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gate = _gate()
    write_json(tmp_path / "PROMOTION_GATE.json", gate)
    write_json(tmp_path / "manifest.json", _manifest(gate))
    _patch_pass_components(monkeypatch)

    result = verification.verify_run_with_lineage(tmp_path)

    assert result["status"] == "PASS"
    report = json.loads((tmp_path / "VERIFICATION_REPORT.json").read_text(encoding="utf-8"))
    assert report["promotion_gate_verification"]["status"] == "PASS"
    assert report["lineage_verification"]["chain_sha256"] == "abc"
    assert report["verification_seal"]["status"] == "PASS"
    assert report["preexisting_verification_seal"] == report["verification_seal"]
    assert (tmp_path / "VERIFICATION_SEAL.json").is_file()
    assert (tmp_path / "SHA256SUMS").is_file()


def test_repeated_standard_verify_is_byte_stable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gate = _gate()
    write_json(tmp_path / "PROMOTION_GATE.json", gate)
    write_json(tmp_path / "manifest.json", _manifest(gate))
    _patch_pass_components(monkeypatch)

    first = verification.verify_run_with_lineage(tmp_path)
    first_report = (tmp_path / "VERIFICATION_REPORT.json").read_bytes()
    first_seal = (tmp_path / "VERIFICATION_SEAL.json").read_bytes()
    first_sums = (tmp_path / "SHA256SUMS").read_bytes()

    second = verification.verify_run_with_lineage(tmp_path)

    assert first["status"] == "PASS"
    assert second["status"] == "PASS"
    assert (tmp_path / "VERIFICATION_REPORT.json").read_bytes() == first_report
    assert (tmp_path / "VERIFICATION_SEAL.json").read_bytes() == first_seal
    assert (tmp_path / "SHA256SUMS").read_bytes() == first_sums
