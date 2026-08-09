from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PipelineLedgerError(RuntimeError):
    """Base error for staged trusted-pipeline ledger failures."""


class PipelineLedgerBlocked(PipelineLedgerError):
    """Raised when evidence is incomplete or validation does not pass."""


@dataclass(frozen=True)
class PipelineDatasetEvidence:
    dataset_id: str
    canonical_sha256: str
    source_sha256: str
    data_version: str
    game_id: str
    series_ids: tuple[str, ...]
    observed_times: tuple[datetime, ...]
    draw_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.observed_times:
            raise ValueError("observed_times must not be empty")
        if len(self.observed_times) != len(self.draw_ids):
            raise ValueError("observed_times and draw_ids must have equal length")
        if not self.series_ids or len(self.series_ids) != len(set(self.series_ids)):
            raise ValueError("series_ids must be non-empty and unique")
        for value in self.observed_times:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("observed_times must be timezone-aware")


@dataclass(frozen=True)
class SliceDraft:
    dataset_id: str
    dataset_sha256: str
    data_role: str
    row_start: int
    row_end: int
    observed_time_start: datetime
    observed_time_end: datetime
    available_at: datetime
    forecast_origin: datetime
    contains_targets: bool
    contains_actuals: bool
    fold_id: str | None = None
    fold_role: str | None = None
    draw_id: str | None = None


@dataclass(frozen=True)
class EventDraft:
    event_id: str
    sequence_no: int
    stage: str
    operation: str
    occurred_at: datetime
    actor: str
    input_slices: tuple[SliceDraft, ...] = ()
    parent_event_ids: tuple[str, ...] = ()
    forecast_origin: datetime | None = None
    forecast_id: str | None = None
    fold_id: str | None = None
    seed: int | None = None
    actuals_known: bool = False
    notes: str = ""


@dataclass(frozen=True)
class PipelineLedgerCloseResult:
    status: str
    run_id: str
    ledger_path: Path
    validation_path: Path
    report_path: Path
    ledger_sha256: str
    verified_events: int
    coverage_gaps: tuple[str, ...]


SealAndValidate = Callable[
    [
        str,
        datetime,
        PipelineDatasetEvidence,
        list[EventDraft],
        list[int],
        Path,
        list[str],
        bool,
    ],
    PipelineLedgerCloseResult,
]
Clock = Callable[[], datetime]


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = absolute_path(path)
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and candidate.is_symlink():
            raise PipelineLedgerBlocked(
                f"{label} must not contain a symlink component: {candidate}"
            )


def atomic_write_json(path: Path, payload: Any) -> None:
    reject_symlink_components(path.parent, label="ledger output")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise PipelineLedgerBlocked(f"ledger artifact is a symlink: {path}")
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
