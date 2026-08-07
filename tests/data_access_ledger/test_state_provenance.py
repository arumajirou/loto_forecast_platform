from __future__ import annotations

from loto.data_access_ledger import (
    AccessOperation,
    FindingCode,
    StateKind,
    validate_ledger,
)

from conftest import HASH_C, make_event, make_ledger, make_slice, make_state


def codes(ledger) -> set[FindingCode]:
    return {item.code for item in validate_ledger(ledger).findings}


def test_state_used_before_fit_is_blocked() -> None:
    train = make_slice()
    state = make_state(
        state_id="missing-state",
        state_kind=StateKind.SCALER,
        fitted_event_id="missing-fit",
        fitted_slice=train,
    )
    event = make_event(
        event_id="transform",
        sequence_no=1,
        operation=AccessOperation.TRANSFORM,
        input_states=[state],
    )
    assert FindingCode.STATE_USED_BEFORE_FIT in codes(make_ledger([event]))


def test_state_hash_mismatch_is_blocked() -> None:
    train = make_slice()
    produced = make_state(
        state_id="scaler",
        state_kind=StateKind.SCALER,
        fitted_event_id="fit-scaler",
        fitted_slice=train,
    )
    fit = make_event(
        event_id="fit-scaler",
        sequence_no=1,
        operation=AccessOperation.FIT_SCALER,
        input_slices=[train],
        output_state=produced,
    )
    mismatched = produced.model_copy(update={"state_sha256": HASH_C})
    transform = make_event(
        event_id="transform",
        sequence_no=2,
        operation=AccessOperation.TRANSFORM,
        input_states=[mismatched],
        parents=[fit.event_id],
    )
    assert FindingCode.STATE_PROVENANCE_MISMATCH in codes(make_ledger([fit, transform]))


def test_fitted_dataset_hash_mismatch_is_blocked() -> None:
    train = make_slice()
    wrong = make_state(
        state_id="model",
        state_kind=StateKind.MODEL,
        fitted_event_id="fit-model",
        fitted_slice=train,
    ).model_copy(update={"fitted_dataset_sha256": HASH_C})
    fit = make_event(
        event_id="fit-model",
        sequence_no=1,
        operation=AccessOperation.FIT_MODEL,
        input_slices=[train],
        output_state=wrong,
    )
    predict = make_event(
        event_id="predict",
        sequence_no=2,
        operation=AccessOperation.PREDICT,
        input_states=[wrong],
        parents=[fit.event_id],
        forecast_id="draw-1",
    )
    assert FindingCode.STATE_PROVENANCE_MISMATCH in codes(make_ledger([fit, predict]))
