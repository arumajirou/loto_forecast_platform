from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from loto.data_access_ledger import AccessDecision, DataAccessLedger, validate_ledger
from loto.orchestration.formal_backtest_ledger import (
    FormalBacktestDatasetEvidence,
    FormalBacktestLedgerBlocked,
    FormalBacktestLedgerRecorder,
)


def evidence() -> FormalBacktestDatasetEvidence:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return FormalBacktestDatasetEvidence(
        dataset_id="loto7-canonical",
        canonical_sha256="a" * 64,
        source_sha256="b" * 64,
        game_id="loto7",
        series_ids=tuple(f"n{i}" for i in range(1, 8)),
        observed_times=tuple(base + timedelta(days=index) for index in range(6)),
        draw_ids=tuple(f"loto7-{index + 1}" for index in range(6)),
    )


def test_recorder_happy_path_is_valid(tmp_path: Path) -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    recorder = FormalBacktestLedgerRecorder(
        run_id="formal-test-run",
        output_dir=tmp_path,
        evidence=evidence(),
        seed=1,
        resume=False,
        clock=lambda: now,
    )
    recorder.register_fold(model_id="baseline", fold_id="fold-4")
    recorder.record_prediction_ready(
        model_id="baseline",
        fold_id="fold-4",
        test_index=3,
    )
    recorder.record_actual_read(
        model_id="baseline",
        fold_id="fold-4",
        test_index=3,
    )
    recorder.record_score(model_id="baseline", fold_id="fold-4")

    report = recorder.close()

    assert report.status is AccessDecision.PASS
    assert report.complete is True
    assert report.expected_folds == 1
    assert report.scored_folds == 1
    ledger_path = tmp_path / "formal_backtest_data_access_ledger.json"
    ledger = DataAccessLedger.model_validate_json(ledger_path.read_text(encoding="utf-8"))
    validation = validate_ledger(ledger)
    assert validation.status is AccessDecision.PASS
    assert [item.operation.value for item in ledger.events] == [
        "READ",
        "FIT_MODEL",
        "PREDICT",
        "READ_ACTUALS",
        "SCORE",
    ]
    assert all(
        left.occurred_at < right.occurred_at
        for left, right in zip(ledger.events, ledger.events[1:], strict=False)
    )


def test_resume_is_rejected_before_events(tmp_path: Path) -> None:
    with pytest.raises(FormalBacktestLedgerBlocked, match="--no-resume"):
        FormalBacktestLedgerRecorder(
            run_id="formal-test-run",
            output_dir=tmp_path,
            evidence=evidence(),
            seed=1,
            resume=True,
        )


def test_actual_read_requires_prediction(tmp_path: Path) -> None:
    recorder = FormalBacktestLedgerRecorder(
        run_id="formal-test-run",
        output_dir=tmp_path,
        evidence=evidence(),
        seed=1,
        resume=False,
    )
    recorder.register_fold(model_id="baseline", fold_id="fold-4")
    with pytest.raises(FormalBacktestLedgerBlocked, match="earlier prediction"):
        recorder.record_actual_read(
            model_id="baseline",
            fold_id="fold-4",
            test_index=3,
        )


def test_incomplete_fold_closes_as_blocked(tmp_path: Path) -> None:
    recorder = FormalBacktestLedgerRecorder(
        run_id="formal-test-run",
        output_dir=tmp_path,
        evidence=evidence(),
        seed=1,
        resume=False,
    )
    recorder.register_fold(model_id="baseline", fold_id="fold-4")
    recorder.record_prediction_ready(
        model_id="baseline",
        fold_id="fold-4",
        test_index=3,
    )
    with pytest.raises(FormalBacktestLedgerBlocked, match="formal backtest ledger blocked"):
        recorder.close()
    report = json.loads(
        (tmp_path / "formal_backtest_data_access_report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "BLOCKED"
    assert any(item.startswith("MISSING_ACTUAL_READS") for item in report["coverage_gaps"])


def test_failure_is_persisted_as_coverage_gap(tmp_path: Path) -> None:
    recorder = FormalBacktestLedgerRecorder(
        run_id="formal-test-run",
        output_dir=tmp_path,
        evidence=evidence(),
        seed=1,
        resume=False,
    )
    recorder.register_fold(model_id="baseline", fold_id="fold-4")
    recorder.record_failure(model_id="baseline", fold_id="fold-4", reason="boom")
    report = json.loads(
        (tmp_path / "formal_backtest_data_access_report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "BLOCKED"
    assert any(item.startswith("FOLD_FAILED:baseline:fold-4") for item in report["coverage_gaps"])
