from __future__ import annotations

from datetime import timedelta

from loto.data_access_ledger import (
    AccessOperation,
    DataRole,
    FindingCode,
    FoldRole,
    Stage,
    StateKind,
    validate_ledger,
)
from tests.data_access_ledger.conftest import BASE, make_event, make_ledger, make_slice, make_state


def codes(ledger) -> set[FindingCode]:
    return {item.code for item in validate_ledger(ledger).findings}


def test_sequence_gap_is_invalid() -> None:
    first = make_event(event_id="first", sequence_no=1, operation=AccessOperation.READ)
    third = make_event(event_id="third", sequence_no=3, operation=AccessOperation.READ)
    assert FindingCode.EVENT_SEQUENCE_GAP in codes(make_ledger([first, third]))


def test_timestamp_reversal_is_invalid() -> None:
    first = make_event(
        event_id="first",
        sequence_no=1,
        operation=AccessOperation.READ,
        occurred_at=BASE + timedelta(hours=2),
    )
    second = make_event(
        event_id="second",
        sequence_no=2,
        operation=AccessOperation.READ,
        occurred_at=BASE + timedelta(hours=1),
    )
    assert FindingCode.TIMESTAMP_ORDER_VIOLATION in codes(make_ledger([first, second]))


def test_parent_missing_is_invalid() -> None:
    event = make_event(
        event_id="consumer",
        sequence_no=1,
        operation=AccessOperation.READ,
        parents=["missing"],
    )
    assert FindingCode.EVENT_PARENT_MISSING in codes(make_ledger([event]))


def test_parent_cycle_is_invalid() -> None:
    first = make_event(
        event_id="first",
        sequence_no=1,
        operation=AccessOperation.READ,
        parents=["second"],
    )
    second = make_event(
        event_id="second",
        sequence_no=2,
        operation=AccessOperation.READ,
        parents=["first"],
    )
    assert FindingCode.EVENT_GRAPH_CYCLE in codes(make_ledger([first, second]))


def test_duplicate_event_id_is_invalid() -> None:
    first = make_event(event_id="duplicate", sequence_no=1, operation=AccessOperation.READ)
    second = make_event(event_id="duplicate", sequence_no=2, operation=AccessOperation.READ)
    assert FindingCode.EVENT_ID_DUPLICATE in codes(make_ledger([first, second]))


def test_chronological_oof_passes() -> None:
    train = make_slice(
        dataset_id="dataset/oof",
        fold_id="fold-1",
        fold_role=FoldRole.TRAIN,
        observed_end=BASE + timedelta(days=50),
    )
    validation = make_slice(
        dataset_id="dataset/oof-validation",
        dataset_sha256="c" * 64,
        data_role=DataRole.VALIDATION,
        row_start=100,
        row_end=119,
        fold_id="fold-1",
        fold_role=FoldRole.VALIDATION,
        observed_start=BASE + timedelta(days=51),
        observed_end=BASE + timedelta(days=60),
    )
    state = make_state(
        state_id="oof-model",
        state_kind=StateKind.MODEL,
        fitted_event_id="oof-fit",
        fitted_slice=train,
    )
    fit = make_event(
        event_id="oof-fit",
        sequence_no=1,
        operation=AccessOperation.FIT_MODEL,
        stage=Stage.OOF,
        input_slices=[train],
        output_state=state,
        fold_id="fold-1",
        seed=42,
    )
    predict = make_event(
        event_id="oof-predict",
        sequence_no=2,
        operation=AccessOperation.PREDICT,
        stage=Stage.OOF,
        input_slices=[validation],
        input_states=[state],
        parents=[fit.event_id],
        fold_id="fold-1",
        seed=42,
    )
    report = validate_ledger(make_ledger([fit, predict], expected_seeds=[42]))
    assert report.error_count == 0


def test_oof_target_fold_cannot_be_fit_input() -> None:
    validation = make_slice(
        data_role=DataRole.VALIDATION,
        fold_id="fold-1",
        fold_role=FoldRole.VALIDATION,
    )
    state = make_state(
        state_id="oof-model",
        state_kind=StateKind.MODEL,
        fitted_event_id="oof-fit",
        fitted_slice=validation,
    )
    fit = make_event(
        event_id="oof-fit",
        sequence_no=1,
        operation=AccessOperation.FIT_MODEL,
        stage=Stage.OOF,
        input_slices=[validation],
        output_state=state,
        fold_id="fold-1",
        seed=42,
    )
    assert FindingCode.OOF_ORDER_VIOLATION in codes(make_ledger([fit]))


def test_future_fold_cannot_be_used_for_calibration() -> None:
    validation = make_slice(
        data_role=DataRole.VALIDATION,
        fold_id="fold-1",
        fold_role=FoldRole.VALIDATION,
    )
    event = make_event(
        event_id="calibrate",
        sequence_no=1,
        operation=AccessOperation.CALIBRATE,
        stage=Stage.OOF,
        input_slices=[validation],
        fold_id="fold-1",
        seed=42,
    )
    assert FindingCode.OOF_ORDER_VIOLATION in codes(make_ledger([event]))
