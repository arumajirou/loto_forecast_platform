from __future__ import annotations

import atexit
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from loto.data_access_ledger import (
    AccessDecision,
    AccessEvent,
    AccessOperation,
    DataRole,
    DatasetSlice,
    FoldRole,
    Stage,
    build_ledger,
    sha256_hex,
    validate_ledger,
)


class FormalBacktestLedgerError(RuntimeError):
    """Base error for instrumented formal-backtest evidence failures."""


class FormalBacktestLedgerBlocked(FormalBacktestLedgerError):
    """Raised after evidence is persisted when the ledger cannot pass."""


@dataclass(frozen=True)
class FormalBacktestDatasetEvidence:
    dataset_id: str
    canonical_sha256: str
    source_sha256: str
    game_id: str
    series_ids: tuple[str, ...]
    observed_times: tuple[datetime, ...]
    draw_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.observed_times:
            raise ValueError("observed_times must not be empty")
        if len(self.observed_times) != len(self.draw_ids):
            raise ValueError("observed_times and draw_ids must have equal length")
        if len(self.series_ids) != len(set(self.series_ids)):
            raise ValueError("series_ids must be unique")
        for value in self.observed_times:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("observed_times must be timezone-aware")


class FormalBacktestLedgerReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: AccessDecision
    run_id: str
    runtime_interception: bool = True
    complete: bool
    ledger_path: str
    validation_path: str
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_folds: int = Field(ge=0)
    scored_folds: int = Field(ge=0)
    coverage_gaps: list[str] = Field(default_factory=list)
    verified_events: int = Field(ge=0)


Clock = Callable[[], datetime]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = _absolute(path)
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and candidate.is_symlink():
            raise FormalBacktestLedgerBlocked(
                f"{label} must not contain a symlink component: {candidate}"
            )


def _atomic_write_json(path: Path, payload: Any) -> None:
    _reject_symlink_components(path.parent, label="ledger output")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise FormalBacktestLedgerBlocked(f"ledger artifact is a symlink: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class FormalBacktestLedgerRecorder:
    """Runtime recorder for the non-resume formal walk-forward lane."""

    def __init__(
        self,
        *,
        run_id: str,
        output_dir: Path,
        evidence: FormalBacktestDatasetEvidence,
        seed: int,
        resume: bool,
        clock: Clock | None = None,
    ) -> None:
        if resume:
            raise FormalBacktestLedgerBlocked(
                "instrumented formal backtest requires --no-resume"
            )
        self.run_id = run_id
        self.output_dir = _absolute(output_dir)
        _reject_symlink_components(self.output_dir, label="output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.evidence = evidence
        self.seed = seed
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_time: datetime | None = None
        self._events: list[AccessEvent] = []
        self._expected: set[tuple[str, str]] = set()
        self._predicted: set[tuple[str, str]] = set()
        self._actual_read: set[tuple[str, str]] = set()
        self._scored: set[tuple[str, str]] = set()
        self._gaps: list[str] = []
        self._closed = False
        self._raw_event_id = self._event_id("read", evidence.canonical_sha256)
        self._append(
            AccessEvent(
                event_id=self._raw_event_id,
                run_id=run_id,
                sequence_no=1,
                stage=Stage.TRAIN,
                operation=AccessOperation.READ,
                occurred_at=self._next_time(),
                actor="scripts.run_formal_model_backtest",
                input_slices=[
                    self._slice(
                        dataset_id=evidence.dataset_id,
                        dataset_sha256=evidence.canonical_sha256,
                        data_role=DataRole.RAW,
                        row_start=0,
                        row_end=len(evidence.observed_times) - 1,
                        forecast_origin=evidence.observed_times[-1],
                        contains_targets=True,
                        contains_actuals=False,
                    )
                ],
                parent_event_ids=[],
                actuals_known=True,
                notes=(
                    "Canonical input loaded for chronological fold slicing; model calls "
                    "receive Train-only frames."
                ),
            )
        )
        atexit.register(self._flush_incomplete)

    @property
    def artifact_paths(self) -> tuple[Path, Path, Path]:
        return (
            self.output_dir / "formal_backtest_data_access_ledger.json",
            self.output_dir / "formal_backtest_data_access_validation.json",
            self.output_dir / "formal_backtest_data_access_report.json",
        )

    def register_fold(self, *, model_id: str, fold_id: str) -> None:
        key = (model_id, fold_id)
        if key in self._expected:
            raise FormalBacktestLedgerBlocked(f"duplicate fold registration: {key}")
        self._expected.add(key)

    def record_prediction_ready(
        self,
        *,
        model_id: str,
        fold_id: str,
        test_index: int,
    ) -> None:
        key = (model_id, fold_id)
        if key not in self._expected:
            raise FormalBacktestLedgerBlocked(f"unregistered fold prediction: {key}")
        if key in self._predicted:
            raise FormalBacktestLedgerBlocked(f"duplicate fold prediction: {key}")
        if test_index <= 0 or test_index >= len(self.evidence.observed_times):
            raise FormalBacktestLedgerBlocked(
                f"invalid test_index for {key}: {test_index}"
            )
        origin = self.evidence.observed_times[test_index]
        train = self._slice(
            dataset_id=self.evidence.dataset_id,
            dataset_sha256=self.evidence.canonical_sha256,
            data_role=DataRole.TRAIN,
            row_start=0,
            row_end=test_index - 1,
            forecast_origin=origin,
            contains_targets=True,
            contains_actuals=False,
            fold_id=fold_id,
            fold_role=FoldRole.TRAIN,
        )
        fit_id = self._event_id("fit", model_id, fold_id, self.seed)
        self._append(
            AccessEvent(
                event_id=fit_id,
                run_id=self.run_id,
                sequence_no=len(self._events) + 1,
                stage=Stage.OOF,
                operation=AccessOperation.FIT_MODEL,
                occurred_at=self._next_time(),
                actor=f"formal-backtest:{model_id}",
                input_slices=[train],
                parent_event_ids=[self._raw_event_id],
                forecast_origin=origin,
                fold_id=fold_id,
                seed=self.seed,
                actuals_known=False,
                notes="Model fit completed using the Train-only frame passed to the worker.",
            )
        )
        identity_hash = sha256_hex(
            {
                "canonical_sha256": self.evidence.canonical_sha256,
                "projection": "forecast_identity",
            }
        )
        identity = self._slice(
            dataset_id=f"{self.evidence.dataset_id}:forecast-identity",
            dataset_sha256=identity_hash,
            data_role=DataRole.VALIDATION,
            row_start=test_index,
            row_end=test_index,
            forecast_origin=origin,
            contains_targets=False,
            contains_actuals=False,
            fold_id=fold_id,
            fold_role=FoldRole.VALIDATION,
            draw_id=self.evidence.draw_ids[test_index],
        )
        self._append(
            AccessEvent(
                event_id=self._event_id("predict", model_id, fold_id, self.seed),
                run_id=self.run_id,
                sequence_no=len(self._events) + 1,
                stage=Stage.OOF,
                operation=AccessOperation.PREDICT,
                occurred_at=self._next_time(),
                actor=f"formal-backtest:{model_id}",
                input_slices=[identity],
                parent_event_ids=[fit_id],
                forecast_origin=origin,
                fold_id=fold_id,
                seed=self.seed,
                actuals_known=False,
                notes=(
                    "Output contract passed before leakage checks or target value "
                    "materialization."
                ),
            )
        )
        self._predicted.add(key)
        self._persist(complete=False)

    def record_actual_read(
        self,
        *,
        model_id: str,
        fold_id: str,
        test_index: int,
    ) -> None:
        key = (model_id, fold_id)
        if key not in self._predicted:
            raise FormalBacktestLedgerBlocked(
                f"actual read requires an earlier prediction: {key}"
            )
        if key in self._actual_read:
            raise FormalBacktestLedgerBlocked(f"duplicate actual read: {key}")
        origin = self.evidence.observed_times[test_index]
        actual_hash = sha256_hex(
            {
                "canonical_sha256": self.evidence.canonical_sha256,
                "projection": "actuals",
            }
        )
        actual = self._slice(
            dataset_id=f"{self.evidence.dataset_id}:actuals",
            dataset_sha256=actual_hash,
            data_role=DataRole.ACTUALS,
            row_start=test_index,
            row_end=test_index,
            forecast_origin=origin,
            contains_targets=True,
            contains_actuals=True,
            fold_id=fold_id,
            fold_role=FoldRole.VALIDATION,
            draw_id=self.evidence.draw_ids[test_index],
        )
        predict_id = self._event_id("predict", model_id, fold_id, self.seed)
        self._append(
            AccessEvent(
                event_id=self._event_id("actual", model_id, fold_id, self.seed),
                run_id=self.run_id,
                sequence_no=len(self._events) + 1,
                stage=Stage.OOF,
                operation=AccessOperation.READ_ACTUALS,
                occurred_at=self._next_time(),
                actor=f"formal-backtest:{model_id}",
                input_slices=[actual],
                parent_event_ids=[predict_id],
                forecast_origin=origin,
                fold_id=fold_id,
                seed=self.seed,
                actuals_known=True,
                notes="Target values materialized only after the prediction hook.",
            )
        )
        self._actual_read.add(key)
        self._persist(complete=False)

    def record_score(self, *, model_id: str, fold_id: str) -> None:
        key = (model_id, fold_id)
        if key not in self._actual_read:
            raise FormalBacktestLedgerBlocked(
                f"score requires an earlier actual read: {key}"
            )
        if key in self._scored:
            raise FormalBacktestLedgerBlocked(f"duplicate fold score: {key}")
        actual_id = self._event_id("actual", model_id, fold_id, self.seed)
        self._append(
            AccessEvent(
                event_id=self._event_id("score", model_id, fold_id, self.seed),
                run_id=self.run_id,
                sequence_no=len(self._events) + 1,
                stage=Stage.OOF,
                operation=AccessOperation.SCORE,
                occurred_at=self._next_time(),
                actor=f"formal-backtest:{model_id}",
                parent_event_ids=[actual_id],
                fold_id=fold_id,
                seed=self.seed,
                actuals_known=True,
                notes="Model metrics and mandatory baseline metrics were persisted.",
            )
        )
        self._scored.add(key)
        self._persist(complete=False)

    def record_failure(self, *, model_id: str, fold_id: str, reason: str) -> None:
        key = f"FOLD_FAILED:{model_id}:{fold_id}:{reason[:200]}"
        if key not in self._gaps:
            self._gaps.append(key)
        self._persist(complete=False)

    def close(self) -> FormalBacktestLedgerReport:
        missing_prediction = sorted(self._expected - self._predicted)
        missing_actual = sorted(self._predicted - self._actual_read)
        missing_score = sorted(self._actual_read - self._scored)
        if missing_prediction:
            self._gaps.append(f"MISSING_PREDICTIONS:{missing_prediction}")
        if missing_actual:
            self._gaps.append(f"MISSING_ACTUAL_READS:{missing_actual}")
        if missing_score:
            self._gaps.append(f"MISSING_SCORES:{missing_score}")
        report = self._persist(complete=True)
        self._closed = True
        atexit.unregister(self._flush_incomplete)
        if report.status is not AccessDecision.PASS:
            raise FormalBacktestLedgerBlocked(
                "formal backtest ledger blocked: " + ", ".join(report.coverage_gaps)
            )
        return report

    def _event_id(self, prefix: str, *parts: object) -> str:
        digest = sha256_hex([self.run_id, prefix, *[str(part) for part in parts]])[:24]
        return f"formal:{prefix}:{digest}"

    def _next_time(self) -> datetime:
        value = _utc(self._clock())
        if self._last_time is not None and value <= self._last_time:
            value = self._last_time + timedelta(microseconds=1)
        self._last_time = value
        return value

    def _slice(
        self,
        *,
        dataset_id: str,
        dataset_sha256: str,
        data_role: DataRole,
        row_start: int,
        row_end: int,
        forecast_origin: datetime,
        contains_targets: bool,
        contains_actuals: bool,
        fold_id: str | None = None,
        fold_role: FoldRole | None = None,
        draw_id: str | None = None,
    ) -> DatasetSlice:
        return DatasetSlice(
            dataset_id=dataset_id,
            dataset_sha256=dataset_sha256,
            data_role=data_role,
            game_id=self.evidence.game_id,
            series_ids=list(self.evidence.series_ids),
            row_start=row_start,
            row_end=row_end,
            observed_time_start=self.evidence.observed_times[row_start],
            observed_time_end=self.evidence.observed_times[row_end],
            available_at=self.evidence.observed_times[row_end],
            forecast_origin=forecast_origin,
            contains_targets=contains_targets,
            contains_actuals=contains_actuals,
            immutable_source=True,
            fold_id=fold_id,
            fold_role=fold_role,
            draw_id=draw_id,
        )

    def _append(self, event: AccessEvent) -> None:
        self._events.append(event)

    def _persist(self, *, complete: bool) -> FormalBacktestLedgerReport:
        ledger = build_ledger(
            run_id=self.run_id,
            created_at=self._events[0].occurred_at,
            events=list(self._events),
            expected_seeds=[self.seed],
        )
        validation = validate_ledger(ledger)
        coverage = list(dict.fromkeys(self._gaps))
        if complete and self._expected != self._scored:
            coverage.append("FOLD_COVERAGE_INCOMPLETE")
        status = (
            AccessDecision.PASS
            if complete
            and validation.status is AccessDecision.PASS
            and not coverage
            else AccessDecision.BLOCKED
        )
        ledger_path, validation_path, report_path = self.artifact_paths
        report = FormalBacktestLedgerReport(
            status=status,
            run_id=self.run_id,
            complete=complete,
            ledger_path=str(ledger_path),
            validation_path=str(validation_path),
            ledger_sha256=ledger.ledger_sha256,
            source_sha256=self.evidence.source_sha256,
            canonical_sha256=self.evidence.canonical_sha256,
            expected_folds=len(self._expected),
            scored_folds=len(self._scored),
            coverage_gaps=coverage,
            verified_events=validation.verified_event_count,
        )
        _atomic_write_json(ledger_path, ledger.model_dump(mode="json"))
        _atomic_write_json(validation_path, validation.model_dump(mode="json"))
        _atomic_write_json(report_path, report.model_dump(mode="json"))
        return report

    def _flush_incomplete(self) -> None:
        if self._closed or not self._events:
            return
        if "RUN_DID_NOT_COMPLETE" not in self._gaps:
            self._gaps.append("RUN_DID_NOT_COMPLETE")
        try:
            self._persist(complete=False)
        except Exception:
            pass


__all__ = [
    "FormalBacktestDatasetEvidence",
    "FormalBacktestLedgerBlocked",
    "FormalBacktestLedgerError",
    "FormalBacktestLedgerRecorder",
    "FormalBacktestLedgerReport",
]
