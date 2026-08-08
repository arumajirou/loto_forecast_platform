from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from loto.orchestration.pipeline_ledger import (
    PipelineDatasetEvidence,
    PipelineLedgerBlocked,
    PipelineLedgerCloseResult,
    PipelineLedgerRecorder,
)


def evidence() -> PipelineDatasetEvidence:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return PipelineDatasetEvidence(
        dataset_id="loto7-canonical",
        canonical_sha256="a" * 64,
        source_sha256="b" * 64,
        data_version="test-v1",
        game_id="loto7",
        series_ids=tuple(f"n{i}" for i in range(1, 8)),
        observed_times=tuple(start + timedelta(days=i) for i in range(10)),
        draw_ids=tuple(f"loto7-{i + 1}" for i in range(10)),
    )


def fake_seal(
    run_id,
    created_at,
    evidence_value,
    drafts,
    expected_seeds,
    output_dir,
    gaps,
    complete,
):
    status = "PASS" if complete and not gaps else "BLOCKED"
    ledger = output_dir / "pipeline_data_access_ledger.json"
    validation = output_dir / "pipeline_data_access_validation.json"
    report = output_dir / "pipeline_data_access_report.json"
    for path in (ledger, validation, report):
        path.write_text("{}\n", encoding="utf-8")
    return PipelineLedgerCloseResult(
        status=status,
        run_id=run_id,
        ledger_path=ledger,
        validation_path=validation,
        report_path=report,
        ledger_sha256="c" * 64,
        verified_events=len(drafts),
        coverage_gaps=tuple(gaps),
    )


def test_recorder_valid_order_and_monotonic_time(tmp_path: Path) -> None:
    constant = datetime(2026, 2, 1, tzinfo=UTC)
    recorder = PipelineLedgerRecorder(
        run_id="pipeline-test",
        output_dir=tmp_path,
        evidence=evidence(),
        clock=lambda: constant,
        seal_validator=fake_seal,
    )
    recorder.register_oof(model_id="uniform", fold_id="fold-9")
    recorder.record_oof_prediction(model_id="uniform", fold_id="fold-9", test_index=8)
    recorder.record_oof_actual(model_id="uniform", fold_id="fold-9", test_index=8)
    recorder.record_oof_score(model_id="uniform", fold_id="fold-9")
    recorder.record_prospective_prediction(
        model_id="uniform",
        forecast_id="forecast-1",
        draw_id="loto7-11",
        forecast_origin=constant + timedelta(days=1),
    )
    recorder.record_prediction_lock(forecast_id="forecast-1", verified=True)
    result = recorder.close()

    assert result.status == "PASS"
    operations = [event.operation for event in recorder.events]
    assert operations == [
        "READ",
        "FIT_MODEL",
        "PREDICT",
        "READ_ACTUALS",
        "SCORE",
        "FIT_MODEL",
        "PREDICT",
        "LOCK_PREDICTION",
    ]
    times = [event.occurred_at for event in recorder.events]
    assert all(left < right for left, right in zip(times, times[1:]))


def test_recorder_rejects_actual_before_prediction(tmp_path: Path) -> None:
    recorder = PipelineLedgerRecorder(
        run_id="pipeline-test",
        output_dir=tmp_path,
        evidence=evidence(),
        seal_validator=fake_seal,
    )
    recorder.register_oof(model_id="uniform", fold_id="fold-9")
    with pytest.raises(PipelineLedgerBlocked, match="requires prediction"):
        recorder.record_oof_actual(model_id="uniform", fold_id="fold-9", test_index=8)


def test_unverified_lock_blocks_close(tmp_path: Path) -> None:
    recorder = PipelineLedgerRecorder(
        run_id="pipeline-test",
        output_dir=tmp_path,
        evidence=evidence(),
        seal_validator=fake_seal,
    )
    recorder.record_prospective_prediction(
        model_id="uniform",
        forecast_id="forecast-1",
        draw_id="loto7-11",
        forecast_origin=datetime(2026, 2, 1, tzinfo=UTC),
    )
    recorder.record_prediction_lock(forecast_id="forecast-1", verified=False)
    with pytest.raises(PipelineLedgerBlocked, match="FORECAST_SEAL_NOT_VERIFIED"):
        recorder.close()


def test_recorder_seals_with_foundation_contract(tmp_path: Path) -> None:
    recorder = PipelineLedgerRecorder(
        run_id="pipeline-integration",
        output_dir=tmp_path,
        evidence=evidence(),
        clock=lambda: datetime(2026, 2, 1, tzinfo=UTC),
    )
    for model_id in ("uniform", "frequency"):
        recorder.register_oof(model_id=model_id, fold_id="fold-9")
        recorder.record_oof_prediction(model_id=model_id, fold_id="fold-9", test_index=8)
        recorder.record_oof_actual(model_id=model_id, fold_id="fold-9", test_index=8)
        recorder.record_oof_score(model_id=model_id, fold_id="fold-9")
    recorder.record_prospective_prediction(
        model_id="uniform",
        forecast_id="forecast-1",
        draw_id="loto7-11",
        forecast_origin=datetime(2026, 2, 1, tzinfo=UTC),
    )
    recorder.record_prediction_lock(forecast_id="forecast-1", verified=True)
    result = recorder.close()
    assert result.status == "PASS"
    report = json.loads(result.validation_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["error_count"] == 0
