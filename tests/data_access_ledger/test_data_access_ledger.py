from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from loto.data_access_ledger import (
    AccessMode,
    AccessPurpose,
    CodeLocation,
    ColumnAccess,
    ColumnRole,
    DataAccessEvent,
    DataAccessLedger,
    LedgerStatus,
    SplitRole,
    TemporalScope,
    TimeBoundary,
    scan_python_source,
    validate_ledger,
)

NOW = datetime(2026, 8, 6, tzinfo=UTC)


def _column(
    name: str = "lag_1",
    *,
    role: ColumnRole = ColumnRole.FEATURE,
    scope: TemporalScope = TemporalScope.PAST_ONLY,
    lag: int = 1,
    known_at: datetime | None = None,
) -> ColumnAccess:
    return ColumnAccess(
        name=name,
        role=role,
        temporal_scope=scope,
        lag=lag,
        known_at=known_at,
    )


def _event(
    event_id: str,
    *,
    sequence: int,
    mode: AccessMode = AccessMode.READ,
    purpose: AccessPurpose = AccessPurpose.FEATURE_BUILD,
    split: SplitRole = SplitRole.TRAIN,
    line: int = 1,
    columns: list[ColumnAccess] | None = None,
    boundary: TimeBoundary | None = None,
    dependencies: list[str] | None = None,
) -> DataAccessEvent:
    return DataAccessEvent(
        event_id=event_id,
        process_id="test-process",
        sequence=sequence,
        mode=mode,
        purpose=purpose,
        split=split,
        dataset="warehouse.draws",
        columns=columns or [_column()],
        boundary=boundary
        or TimeBoundary(
            end=NOW - timedelta(days=1),
            prediction_cutoff=NOW,
            available_at=NOW - timedelta(days=1),
        ),
        location=CodeLocation(path="src/example.py", line=line, symbol="run"),
        dependencies=dependencies or [],
    )


def _ledger(*events: DataAccessEvent) -> DataAccessLedger:
    return DataAccessLedger(
        ledger_id="ledger-test-v1",
        generated_at=NOW,
        code_revision="0" * 40,
        events=list(events),
    )


def _codes(ledger: DataAccessLedger) -> set[str]:
    return {finding.code for finding in validate_ledger(ledger).findings}


def test_safe_train_ledger_passes() -> None:
    read = _event("read-train", sequence=1)
    fit = _event(
        "fit-train",
        sequence=2,
        mode=AccessMode.FIT,
        purpose=AccessPurpose.MODEL_FIT,
        dependencies=[read.event_id],
    )

    report = validate_ledger(_ledger(read, fit))

    assert report.status is LedgerStatus.PASS
    assert report.findings == []
    assert report.passed is True


def test_contracts_forbid_unknown_fields_and_noncausal_event_order() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TimeBoundary(end=NOW, unknown=True)

    late = _event("late-event", sequence=2)
    early = _event("early-event", sequence=1)
    with pytest.raises(ValidationError, match="events must be sorted"):
        _ledger(late, early)


def test_future_access_and_post_cutoff_column_are_rejected() -> None:
    event = _event(
        "validation-read",
        sequence=1,
        split=SplitRole.VALIDATION,
        boundary=TimeBoundary(
            end=NOW + timedelta(seconds=1),
            prediction_cutoff=NOW,
            available_at=NOW + timedelta(seconds=1),
        ),
        columns=[_column(known_at=NOW + timedelta(seconds=1))],
    )

    assert _codes(_ledger(event)) == {
        "COLUMN_NOT_AVAILABLE_AT_CUTOFF",
        "DATASET_NOT_AVAILABLE_AT_CUTOFF",
        "FUTURE_WINDOW_ACCESS",
    }


def test_fit_holdout_and_current_target_feature_are_rejected() -> None:
    target = _column(
        "n1",
        role=ColumnRole.TARGET,
        scope=TemporalScope.TARGET,
        lag=0,
    )
    event = _event(
        "holdout-fit",
        sequence=1,
        mode=AccessMode.FIT,
        purpose=AccessPurpose.FEATURE_BUILD,
        split=SplitRole.HOLDOUT,
        columns=[target],
    )

    assert _codes(_ledger(event)) == {
        "CURRENT_TARGET_AS_FEATURE",
        "FIT_OUTSIDE_TRAIN",
        "HOLDOUT_USED_FOR_SELECTION",
    }


def test_dependency_must_exist_precede_event_and_not_come_from_later_split() -> None:
    future = _event(
        "future-holdout",
        sequence=2,
        split=SplitRole.HOLDOUT,
        purpose=AccessPurpose.EVALUATION,
    )
    train = _event(
        "train-consumer",
        sequence=1,
        dependencies=[future.event_id, "missing-event"],
    )

    assert _codes(_ledger(train, future)) == {
        "FUTURE_SPLIT_DEPENDENCY",
        "NON_CAUSAL_DEPENDENCY_ORDER",
        "UNKNOWN_DEPENDENCY",
    }


def test_ast_scanner_requires_matching_mode_at_exact_line() -> None:
    source = "\n".join(
        [
            "import pandas as pd",
            "frame = pd.read_parquet('draws.parquet')",
            "model.fit(frame)",
            "joined = frame.merge(frame, on='draw_no')",
        ]
    )
    read = _event("read-source", sequence=1, line=2)
    wrong_fit = _event("wrong-fit", sequence=2, mode=AccessMode.READ, line=3)
    ledger = _ledger(read, wrong_fit)

    findings = scan_python_source(source, path="src/example.py", ledger=ledger)

    assert [(item.code, item.line, item.expected_mode) for item in findings] == [
        ("ACCESS_MODE_MISMATCH", 3, AccessMode.FIT),
        ("UNDECLARED_DATA_ACCESS", 4, AccessMode.JOIN),
    ]


def test_ast_scanner_resolves_from_import_alias() -> None:
    source = "from pandas import read_csv as load\nframe = load('draws.csv')\n"
    event = _event("read-csv", sequence=1, line=2)

    assert scan_python_source(source, path="src/example.py", ledger=_ledger(event)) == []
