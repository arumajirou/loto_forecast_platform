from __future__ import annotations

import hashlib
import importlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.coverage.ledger import (
    CoverageDatasetEvidence,
    CoverageLedgerPreflightError,
    git_blob_sha,
    require_regular_file,
)

EXPECTED_COVERAGE_RUNNER_BLOB_SHA = "8a09c5deab4798bbe604c732f797d9746af84b77"
EXPECTED_AUTO_RESEARCH_BLOB_SHA = "e2dbdb3d10c49f81eb80ac7c53f4d66ec7835a20"


def module(name: str) -> Any:
    return importlib.import_module(name)


def absolute(path: str | Path) -> Path:
    return Path(path).expanduser().absolute()


def count_csv_rows(path: Path) -> int:
    with path.open("rb") as handle:
        line_count = sum(1 for _ in handle)
    return max(0, line_count - 1)


def utc(value: Any) -> datetime:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        raise CoverageLedgerPreflightError("draw_date must contain datetime values")
    if value.tzinfo is None or value.utcoffset() is None:
        raise CoverageLedgerPreflightError("draw_date values must be timezone-aware")
    return value.astimezone(UTC)


def draw_ids(frame: Any, game: str) -> tuple[str, ...]:
    if "draw_id" in frame.columns:
        return tuple(str(value) for value in frame["draw_id"].tolist())
    if "draw_no" in frame.columns:
        return tuple(f"{game}-{int(value)}" for value in frame["draw_no"].tolist())
    return tuple(f"{game}-row-{index + 1}" for index in range(len(frame)))


def frame_hash(frame: Any) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_pin(*, source: Path, expected: str, label: str) -> None:
    require_regular_file(source, label=label)
    observed = git_blob_sha(source)
    if observed != expected:
        raise CoverageLedgerPreflightError(
            f"{label} source pin mismatch: expected={expected} observed={observed}"
        )


def make_evidence(
    *,
    frame: Any,
    dataset_id: str,
    dataset_sha256: str,
    game: str,
    source_total_rows: int,
    protected_test_start: int,
    count: int,
) -> CoverageDatasetEvidence:
    if "draw_date" not in frame.columns:
        raise CoverageLedgerPreflightError(f"{game}: instrumented lane requires a draw_date column")
    observed_times = tuple(utc(value) for value in frame["draw_date"].tolist())
    if any(left >= right for left, right in zip(observed_times, observed_times[1:])):
        raise CoverageLedgerPreflightError(f"{game}: draw_date must be strictly increasing")
    return CoverageDatasetEvidence(
        dataset_id=dataset_id,
        dataset_sha256=dataset_sha256,
        game_id=game,
        series_ids=tuple(f"n{index}" for index in range(1, count + 1)),
        observed_times=observed_times,
        draw_ids=draw_ids(frame, game),
        source_total_rows=source_total_rows,
        accessible_rows=len(frame),
        protected_test_start=protected_test_start,
        protected_test_end=source_total_rows,
    )


def run_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
