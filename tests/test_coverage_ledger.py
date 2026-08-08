from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from loto.coverage.ledger import (
    CoverageDatasetEvidence,
    CoverageLedgerBlocked,
    CoverageLedgerRecorder,
)


def evidence() -> CoverageDatasetEvidence:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return CoverageDatasetEvidence(
        dataset_id="coverage-loto7-prefix",
        dataset_sha256="a" * 64,
        game_id="loto7",
        series_ids=tuple(f"n{i}" for i in range(1, 8)),
        observed_times=tuple(start + timedelta(days=i) for i in range(10)),
        draw_ids=tuple(f"loto7-{i + 1}" for i in range(10)),
        source_total_rows=12,
        accessible_rows=10,
        protected_test_start=10,
        protected_test_end=12,
    )


def test_valid_fold_order_seals_with_foundation(tmp_path: Path) -> None:
    constant = datetime(2026, 2, 1, tzinfo=UTC)
    recorder = CoverageLedgerRecorder(
        run_id="coverage-test",
        output_dir=tmp_path,
        evidence=evidence(),
        expected_seeds=[0],
        clock=lambda: constant,
    )
    for phase, index in (("calibration", 8), ("validation", 9)):
        fold_id = recorder.register_fold(
            experiment_id="experiment-1",
            model_id="median",
            phase=phase,
            test_index=index,
            seed=0,
        )
        recorder.record_prediction(fold_id=fold_id)
        recorder.record_actual(fold_id=fold_id)
        recorder.record_score(fold_id=fold_id)

    result = recorder.close()

    assert result.status == "PASS"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["protected_test_evaluated"] is False
    assert report["protected_test_materialized"] is False
    validation = json.loads(result.validation_path.read_text(encoding="utf-8"))
    assert validation["status"] == "PASS"
    operations = [event.operation.value for event in recorder.events]
    assert operations == [
        "READ",
        "FIT_MODEL",
        "PREDICT",
        "READ_ACTUALS",
        "SCORE",
        "FIT_MODEL",
        "PREDICT",
        "READ_ACTUALS",
        "SCORE",
    ]
    times = [event.occurred_at for event in recorder.events]
    assert all(left < right for left, right in zip(times, times[1:], strict=False))


def test_actual_before_prediction_is_rejected(tmp_path: Path) -> None:
    recorder = CoverageLedgerRecorder(
        run_id="coverage-test",
        output_dir=tmp_path,
        evidence=evidence(),
        expected_seeds=[0],
    )
    fold_id = recorder.register_fold(
        experiment_id="experiment-1",
        model_id="median",
        phase="validation",
        test_index=9,
        seed=0,
    )
    with pytest.raises(CoverageLedgerBlocked, match="earlier prediction"):
        recorder.record_actual(fold_id=fold_id)


def test_missing_score_blocks_and_persists_report(tmp_path: Path) -> None:
    recorder = CoverageLedgerRecorder(
        run_id="coverage-test",
        output_dir=tmp_path,
        evidence=evidence(),
        expected_seeds=[0],
    )
    fold_id = recorder.register_fold(
        experiment_id="experiment-1",
        model_id="median",
        phase="validation",
        test_index=9,
        seed=0,
    )
    recorder.record_prediction(fold_id=fold_id)
    recorder.record_actual(fold_id=fold_id)

    with pytest.raises(CoverageLedgerBlocked, match="FOLD_SCORE_MISSING"):
        recorder.close()

    report = json.loads((tmp_path / "coverage_data_access_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "BLOCKED"
    assert any("FOLD_SCORE_MISSING" in item for item in report["coverage_gaps"])
