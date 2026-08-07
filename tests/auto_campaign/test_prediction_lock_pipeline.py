from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import lineage_pipeline as pipeline
from loto.auto_campaign.contracts import CampaignStage
from loto.auto_campaign.persistence import write_json


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


def _prepare_common(monkeypatch: pytest.MonkeyPatch, stage: CampaignStage) -> None:
    monkeypatch.setattr(
        pipeline,
        "evaluate_lineage_inputs",
        lambda **_kwargs: _pass_lineage_input(stage),
    )
    monkeypatch.setattr(
        pipeline,
        "evaluate_promotion_gate",
        lambda **_kwargs: _pass_gate(stage),
    )
    monkeypatch.setattr(pipeline, "_input_verification_failures", lambda **_kwargs: [])
    monkeypatch.setattr(
        pipeline,
        "run_stage_with_promotion_gate",
        lambda **_kwargs: {"status": "PASS", "stage": stage.value},
    )
    monkeypatch.setattr(
        pipeline,
        "write_run_lineage",
        lambda **_kwargs: {
            "status": "PASS",
            "stage": stage.value,
            "lineage_status": "PASS",
        },
    )


def test_prospective_stage_locks_after_lineage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _prepare_common(monkeypatch, CampaignStage.PROSPECTIVE)
    calls: list[str] = []

    def fake_lock(run_root: Path) -> dict[str, Any]:
        calls.append(str(run_root))
        return {
            "status": "PASS",
            "prediction_lock_status": "LOCKED",
            "prediction_task_count": 36,
        }

    monkeypatch.setattr(pipeline, "freeze_prospective_predictions", fake_lock)
    run_root = tmp_path / "prospective"

    result = pipeline.run_stage_with_promotion_and_lineage(
        runner=lambda *_args, **_kwargs: {"status": "PASS"},
        project_root=tmp_path,
        config=object(),
        run_root=run_root,
        target_stage=CampaignStage.PROSPECTIVE,
        source_run=tmp_path / "validation",
        predecessor_run=tmp_path / "holdout",
        coverage_run=tmp_path / "coverage",
        runtime_run=None,
        resume=False,
    )

    assert result["status"] == "PASS"
    assert result["lineage_status"] == "PASS"
    assert result["prediction_lock_status"] == "LOCKED"
    assert result["prediction_task_count"] == 36
    assert calls == [str(run_root)]


def test_nonprospective_stage_does_not_call_prediction_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _prepare_common(monkeypatch, CampaignStage.HOLDOUT)
    monkeypatch.setattr(
        pipeline,
        "freeze_prospective_predictions",
        lambda _root: pytest.fail("holdout must not create a prediction lock"),
    )

    result = pipeline.run_stage_with_promotion_and_lineage(
        runner=lambda *_args, **_kwargs: {"status": "PASS"},
        project_root=tmp_path,
        config=object(),
        run_root=tmp_path / "holdout",
        target_stage=CampaignStage.HOLDOUT,
        source_run=tmp_path / "validation",
        predecessor_run=tmp_path / "oof",
        coverage_run=tmp_path / "coverage",
        runtime_run=None,
        resume=False,
    )

    assert result["status"] == "PASS"
    assert result["lineage_status"] == "PASS"
    assert "prediction_lock_status" not in result


def test_lock_failure_marks_run_partial_and_writes_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _prepare_common(monkeypatch, CampaignStage.PROSPECTIVE)
    run_root = tmp_path / "prospective"
    run_root.mkdir()
    write_json(
        run_root / "manifest.json",
        {
            "status": "PASS",
            "stage": "prospective",
            "lineage_status": "PASS",
        },
    )

    def fail_lock(_root: Path) -> dict[str, Any]:
        raise ValueError("prediction artifact changed before lock")

    monkeypatch.setattr(pipeline, "freeze_prospective_predictions", fail_lock)

    result = pipeline.run_stage_with_promotion_and_lineage(
        runner=lambda *_args, **_kwargs: {"status": "PASS"},
        project_root=tmp_path,
        config=object(),
        run_root=run_root,
        target_stage=CampaignStage.PROSPECTIVE,
        source_run=tmp_path / "validation",
        predecessor_run=tmp_path / "holdout",
        coverage_run=tmp_path / "coverage",
        runtime_run=None,
        resume=False,
    )

    assert result["status"] == "PARTIAL"
    assert result["prediction_lock_status"] == "FAILED"
    assert (run_root / "PREDICTION_LOCK_FAILURE.json").is_file()
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PARTIAL"
    assert manifest["prediction_lock_status"] == "FAILED"
    assert manifest["actual_known_at_lock"] == "UNKNOWN"
    assert (run_root / "SHA256SUMS").is_file()
