from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class CoverageLedgerError(RuntimeError):
    """Base error for coverage-ledger execution."""


class CoverageLedgerPreflightError(CoverageLedgerError):
    """Raised before execution when the safe coverage lane is unavailable."""


class CoverageLedgerBlocked(CoverageLedgerError):
    """Raised when emitted coverage evidence is incomplete or invalid."""


@dataclass(frozen=True)
class CoverageDatasetEvidence:
    dataset_id: str
    dataset_sha256: str
    game_id: str
    series_ids: tuple[str, ...]
    observed_times: tuple[datetime, ...]
    draw_ids: tuple[str, ...]
    source_total_rows: int
    accessible_rows: int
    protected_test_start: int
    protected_test_end: int

    def __post_init__(self) -> None:
        if not self.dataset_id or not self.game_id:
            raise ValueError("dataset_id and game_id are required")
        if len(self.dataset_sha256) != 64:
            raise ValueError("dataset_sha256 must be 64 hexadecimal characters")
        if not self.series_ids:
            raise ValueError("series_ids must not be empty")
        if self.accessible_rows < 2:
            raise ValueError("accessible_rows must be at least 2")
        if len(self.observed_times) != self.accessible_rows:
            raise ValueError("observed_times must match accessible_rows")
        if len(self.draw_ids) != self.accessible_rows:
            raise ValueError("draw_ids must match accessible_rows")
        if self.protected_test_start != self.accessible_rows:
            raise ValueError("protected test must start after accessible rows")
        if self.protected_test_end != self.source_total_rows:
            raise ValueError("protected test end must match source_total_rows")
        for value in self.observed_times:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("observed_times must be timezone-aware")
            if value.utcoffset() != UTC.utcoffset(value):
                raise ValueError("observed_times must use UTC")


@dataclass(frozen=True)
class CoverageLedgerCloseResult:
    status: str
    run_id: str
    ledger_path: Path
    validation_path: Path
    report_path: Path
    ledger_sha256: str
    verified_events: int
    coverage_gaps: tuple[str, ...]


@dataclass
class FoldState:
    experiment_id: str
    model_id: str
    fold_id: str
    seed: int
    phase: str
    test_index: int
    fit_event_id: str
    predicted: bool = False
    actual_read: bool = False
    scored: bool = False
    predict_event_id: str | None = None
    actual_event_id: str | None = None


Clock = Callable[[], datetime]
