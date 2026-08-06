from __future__ import annotations

from loto.data_access_ledger.contracts import (
    AccessMode,
    AccessPurpose,
    ColumnRole,
    DataAccessLedger,
    LedgerFinding,
    LedgerReport,
    LedgerStatus,
    SplitRole,
    TemporalScope,
)

_FIT_MODES = {AccessMode.FIT, AccessMode.TRANSFORM_FIT}
_DATA_CONSUMING_MODES = {
    AccessMode.READ,
    AccessMode.FIT,
    AccessMode.TRANSFORM_FIT,
    AccessMode.TRANSFORM_APPLY,
    AccessMode.JOIN,
    AccessMode.AGGREGATE,
    AccessMode.LABEL,
    AccessMode.SCORE,
}
_SELECTION_PURPOSES = {
    AccessPurpose.MODEL_FIT,
    AccessPurpose.MODEL_SELECTION,
    AccessPurpose.HYPERPARAMETER_TUNING,
    AccessPurpose.FEATURE_BUILD,
}
_CUTOFF_REQUIRED_PURPOSES = {
    AccessPurpose.FEATURE_BUILD,
    AccessPurpose.MODEL_FIT,
    AccessPurpose.MODEL_SELECTION,
    AccessPurpose.HYPERPARAMETER_TUNING,
    AccessPurpose.EVALUATION,
    AccessPurpose.SCORING,
}
_SPLIT_RANK = {
    SplitRole.RAW: 0,
    SplitRole.TRAIN: 1,
    SplitRole.VALIDATION: 2,
    SplitRole.HOLDOUT: 3,
    SplitRole.PROSPECTIVE: 4,
    SplitRole.ACTUAL: 5,
}


def _finding(code: str, event_id: str, message: str) -> LedgerFinding:
    return LedgerFinding(code=code, event_id=event_id, message=message)


def validate_ledger(ledger: DataAccessLedger) -> LedgerReport:
    findings: list[LedgerFinding] = []
    events_by_id = {event.event_id: event for event in ledger.events}

    for event in ledger.events:
        if event.mode in _FIT_MODES and event.split is not SplitRole.TRAIN:
            findings.append(
                _finding(
                    "FIT_OUTSIDE_TRAIN",
                    event.event_id,
                    f"{event.mode.value} is only allowed on the train split",
                )
            )

        if event.mode in _DATA_CONSUMING_MODES and event.boundary.end is None:
            findings.append(
                _finding(
                    "UNBOUNDED_EVENT_WINDOW",
                    event.event_id,
                    f"{event.mode.value} requires a bounded end timestamp",
                )
            )

        if (
            event.purpose in _CUTOFF_REQUIRED_PURPOSES
            and event.boundary.prediction_cutoff is None
        ):
            findings.append(
                _finding(
                    "MISSING_PREDICTION_CUTOFF",
                    event.event_id,
                    f"{event.purpose.value} requires prediction_cutoff",
                )
            )

        if (
            event.purpose in _CUTOFF_REQUIRED_PURPOSES
            and event.boundary.available_at is None
        ):
            findings.append(
                _finding(
                    "MISSING_DATASET_AVAILABILITY_EVIDENCE",
                    event.event_id,
                    f"{event.purpose.value} requires dataset available_at evidence",
                )
            )

        cutoff = event.boundary.prediction_cutoff
        if cutoff is not None:
            if event.boundary.end is not None and event.boundary.end > cutoff:
                findings.append(
                    _finding(
                        "FUTURE_WINDOW_ACCESS",
                        event.event_id,
                        "read window ends after prediction_cutoff",
                    )
                )
            if event.boundary.available_at is not None and event.boundary.available_at > cutoff:
                findings.append(
                    _finding(
                        "DATASET_NOT_AVAILABLE_AT_CUTOFF",
                        event.event_id,
                        "dataset became available after prediction_cutoff",
                    )
                )

        if event.split is SplitRole.HOLDOUT and event.purpose in _SELECTION_PURPOSES:
            findings.append(
                _finding(
                    "HOLDOUT_USED_FOR_SELECTION",
                    event.event_id,
                    f"holdout split cannot be used for {event.purpose.value}",
                )
            )

        if event.split in {SplitRole.PROSPECTIVE, SplitRole.ACTUAL} and event.purpose not in {
            AccessPurpose.SCORING,
            AccessPurpose.ACTUAL_INGESTION,
            AccessPurpose.AUDIT,
            AccessPurpose.EXPORT,
        }:
            findings.append(
                _finding(
                    "PROSPECTIVE_DATA_USED_EARLY",
                    event.event_id,
                    f"{event.split.value} data cannot be used for {event.purpose.value}",
                )
            )

        for column in event.columns:
            if column.temporal_scope is TemporalScope.UNBOUNDED:
                findings.append(
                    _finding(
                        "UNBOUNDED_TEMPORAL_ACCESS",
                        event.event_id,
                        f"column {column.name!r} has unbounded temporal scope",
                    )
                )
            if cutoff is not None and column.known_at is not None and column.known_at > cutoff:
                findings.append(
                    _finding(
                        "COLUMN_NOT_AVAILABLE_AT_CUTOFF",
                        event.event_id,
                        f"column {column.name!r} became known after prediction_cutoff",
                    )
                )
            if (
                column.role in {ColumnRole.TARGET, ColumnRole.ACTUAL}
                and column.lag == 0
                and event.purpose is AccessPurpose.FEATURE_BUILD
            ):
                findings.append(
                    _finding(
                        "CURRENT_TARGET_AS_FEATURE",
                        event.event_id,
                        f"current target/actual column {column.name!r} is used for feature_build",
                    )
                )
            if (
                column.temporal_scope is TemporalScope.FUTURE_KNOWN
                and column.known_at is None
            ):
                findings.append(
                    _finding(
                        "UNVERIFIED_FUTURE_KNOWN_COLUMN",
                        event.event_id,
                        f"future-known column {column.name!r} has no known_at evidence",
                    )
                )

        for dependency_id in event.dependencies:
            dependency = events_by_id.get(dependency_id)
            if dependency is None:
                findings.append(
                    _finding(
                        "UNKNOWN_DEPENDENCY",
                        event.event_id,
                        f"dependency {dependency_id!r} does not exist",
                    )
                )
                continue
            if dependency.sequence >= event.sequence:
                findings.append(
                    _finding(
                        "NON_CAUSAL_DEPENDENCY_ORDER",
                        event.event_id,
                        f"dependency {dependency_id!r} is not earlier in the ledger",
                    )
                )
            if _SPLIT_RANK[dependency.split] > _SPLIT_RANK[event.split]:
                findings.append(
                    _finding(
                        "FUTURE_SPLIT_DEPENDENCY",
                        event.event_id,
                        f"{event.split.value} event depends on later split "
                        f"{dependency.split.value}",
                    )
                )
            if cutoff is not None:
                dependency_end = dependency.boundary.end
                if dependency_end is not None and dependency_end > cutoff:
                    findings.append(
                        _finding(
                            "DEPENDENCY_WINDOW_AFTER_CUTOFF",
                            event.event_id,
                            f"dependency {dependency_id!r} ends after prediction_cutoff",
                        )
                    )
                dependency_available_at = dependency.boundary.available_at
                if dependency_available_at is not None and dependency_available_at > cutoff:
                    findings.append(
                        _finding(
                            "DEPENDENCY_NOT_AVAILABLE_AT_CUTOFF",
                            event.event_id,
                            f"dependency {dependency_id!r} was unavailable at prediction_cutoff",
                        )
                    )

    findings.sort(key=lambda item: (item.event_id, item.code, item.message))
    status = LedgerStatus.FAIL if findings else LedgerStatus.PASS
    return LedgerReport(ledger_id=ledger.ledger_id, status=status, findings=findings)
