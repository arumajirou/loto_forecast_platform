from __future__ import annotations

from collections.abc import Iterable

from loto.data_access_ledger.canonical import sha256_hex
from loto.data_access_ledger.contracts import DatasetSlice
from loto.data_access_ledger.enums import (
    AccessOperation,
    FindingCode,
    FindingSeverity,
    StateKind,
)
from loto.data_access_ledger.report import ValidationFinding

FIT_ONLY_OPERATIONS = {
    AccessOperation.FIT_MODEL,
    AccessOperation.FIT_SCALER,
    AccessOperation.FIT_ENCODER,
    AccessOperation.SELECT_FEATURES,
}
AVAILABILITY_OPERATIONS = FIT_ONLY_OPERATIONS | {
    AccessOperation.TUNE,
    AccessOperation.CALIBRATE,
    AccessOperation.PREDICT,
}
HOLDOUT_FORBIDDEN = FIT_ONLY_OPERATIONS | {AccessOperation.TUNE}
STATE_PRODUCER = {
    StateKind.MODEL: AccessOperation.FIT_MODEL,
    StateKind.SCALER: AccessOperation.FIT_SCALER,
    StateKind.ENCODER: AccessOperation.FIT_ENCODER,
    StateKind.FEATURE_SELECTOR: AccessOperation.SELECT_FEATURES,
    StateKind.CALIBRATOR: AccessOperation.CALIBRATE,
    StateKind.HPO_RESULT: AccessOperation.TUNE,
}
INVALID_CODES = {
    FindingCode.EVENT_ID_DUPLICATE,
    FindingCode.EVENT_SEQUENCE_GAP,
    FindingCode.EVENT_PARENT_MISSING,
    FindingCode.EVENT_GRAPH_CYCLE,
    FindingCode.TIMESTAMP_ORDER_VIOLATION,
    FindingCode.LEDGER_HASH_MISMATCH,
    FindingCode.RUN_ID_MISMATCH,
    FindingCode.EVENT_COUNT_MISMATCH,
    FindingCode.EVENT_TIME_BOUNDARY_MISMATCH,
    FindingCode.EVENT_PARENT_NOT_PREVIOUS,
    FindingCode.EVENT_ORDER_MISMATCH,
    FindingCode.DATASET_HASH_MISMATCH,
}


def finding(
    code: FindingCode,
    *,
    event_id: str = "__ledger__",
    related: Iterable[str] = (),
    message: str,
    expected: str = "",
    observed: str = "",
    severity: FindingSeverity = FindingSeverity.ERROR,
) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        severity=severity,
        event_id=event_id,
        related_event_ids=list(related),
        message=message,
        expected=expected,
        observed=observed,
    )


def slice_signature(slices: list[DatasetSlice]) -> str:
    payload = [
        {
            "dataset_sha256": item.dataset_sha256,
            "row_start": item.row_start,
            "row_end": item.row_end,
            "observed_time_start": item.observed_time_start,
            "observed_time_end": item.observed_time_end,
            "fold_id": item.fold_id,
            "fold_role": item.fold_role,
        }
        for item in slices
    ]
    return sha256_hex(payload)
