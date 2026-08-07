from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import lineage_pipeline as pipeline
from loto.auto_campaign.contracts import CampaignStage


def _pass_gate(stage: CampaignStage) -> dict[str, Any]:
    return {
        "schema_version": "all-auto-promotion-gate-v1",
        "status": "PASS",
        "target_stage": stage.value,
        "failures": [],
    }


def _pass_lineage_input(stage: CampaignStage) -> dict[str, Any]:
    return {
        "schema_version": "all-auto-lineage-input-check-v1",
        "status": "PASS",
        "target_stage": stage.value,
        "failures": [],
    }


def test_invalid_lineage_blocks_before_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "holdout"
    called = False

    def runner(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"status": "PASS"}

    monkeypatch.setattr(
        pipeline,
        "evaluate_lineage_inputs",
        lambda **_kwargs: {
            "status": "BLOCKED",
            "target_stage": "holdout",
            "failures": ["holdout requires predecessor stage=oof"],
        },
    )
    monkeypatch.setattr(
        pipeline,
        "evaluate_promotion_gate",
        lambda **_kwargs: _pass_gate(CampaignStage.HOLDOUT),
    )
    monkeypatch.setattr(pipeline, "_input_verification_failures", lambda **_kwargs: [])

    result = pipeline.run_stage_with_promotion_and_lineage(
        runner=runner,
        project_root=tmp_path,
        config=object(),
        run_root=output,
        target_stage=CampaignStage.HOLDOUT,
        source_run=tmp_path / "validation",
        predecessor_run=None,
        coverage_run=tmp_path / "coverage",
        runtime_run=None,
        resume=False,
    )

    assert result["status"] == "BLOCKED"
    assert called is False
    assert not output.exists()
    sidecar = tmp_path / "holdout.PROMOTION_GATE_BLOCKED.json"
    assert sidecar.is_file()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["lineage_input"]["status"] == "BLOCKED"


def test_nonpass_stage_does_not_write_lineage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lineage_written = False
    monkeypatch.setattr(
        pipeline,
        "evaluate_lineage_inputs",
        lambda **_kwargs: _pass_lineage_input(CampaignStage.HPO),
    )
    monkeypatch.setattr(
        pipeline,
        "evaluate_promotion_gate",
        lambda **_kwargs: _pass_gate(CampaignStage.HPO),
    )
    monkeypatch.setattr(pipeline, "_input_verification_failures", lambda **_kwargs: [])
    monkeypatch.setattr(
        pipeline,
        "run_stage_with_promotion_gate",
        lambda **_kwargs: {"status": "PARTIAL", "stage": "hpo"},
    )

    def fake_lineage(**_kwargs: Any) -> dict[str, Any]:
        nonlocal lineage_written
        lineage_written = True
        return {"status": "PASS"}

    monkeypatch.setattr(pipeline, "write_run_lineage", fake_lineage)

    result = pipeline.run_stage_with_promotion_and_lineage(
        runner=lambda *_args, **_kwargs: {"status": "PASS"},
        project_root=tmp_path,
        config=object(),
        run_root=tmp_path / "hpo",
        target_stage=CampaignStage.HPO,
        source_run=None,
        predecessor_run=None,
        coverage_run=tmp_path / "coverage",
        runtime_run=None,
        resume=False,
    )

    assert result["status"] == "PARTIAL"
    assert result["lineage_status"] == "NOT_WRITTEN_RUN_NOT_PASS"
    assert lineage_written is False


def test_passed_stage_forwards_predecessor_to_lineage_writer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    predecessor = tmp_path / "oof"
    source = tmp_path / "validation"
    coverage = tmp_path / "coverage"
    monkeypatch.setattr(
        pipeline,
        "evaluate_lineage_inputs",
        lambda **_kwargs: _pass_lineage_input(CampaignStage.HOLDOUT),
    )
    monkeypatch.setattr(
        pipeline,
        "evaluate_promotion_gate",
        lambda **_kwargs: _pass_gate(CampaignStage.HOLDOUT),
    )
    monkeypatch.setattr(pipeline, "_input_verification_failures", lambda **_kwargs: [])
    monkeypatch.setattr(
        pipeline,
        "run_stage_with_promotion_gate",
        lambda **_kwargs: {"status": "PASS", "stage": "holdout"},
    )

    def fake_lineage(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "PASS", "lineage_status": "PASS"}

    monkeypatch.setattr(pipeline, "write_run_lineage", fake_lineage)

    result = pipeline.run_stage_with_promotion_and_lineage(
        runner=lambda *_args, **_kwargs: {"status": "PASS"},
        project_root=tmp_path,
        config=object(),
        run_root=tmp_path / "holdout",
        target_stage=CampaignStage.HOLDOUT,
        source_run=source,
        predecessor_run=predecessor,
        coverage_run=coverage,
        runtime_run=None,
        resume=False,
    )

    assert result["status"] == "PASS"
    assert captured["source_run"] == source
    assert captured["predecessor_run"] == predecessor
    assert captured["coverage_run"] == coverage
    assert captured["target_stage"] == CampaignStage.HOLDOUT
