from __future__ import annotations

from loto.data_access_ledger import (
    AccessDecision,
    AccessOperation,
    DataRole,
    FindingCode,
    Stage,
    StateKind,
    validate_ledger,
)
from tests.data_access_ledger.conftest import make_event, make_ledger, make_slice, make_state


def codes(ledger) -> set[FindingCode]:
    return {item.code for item in validate_ledger(ledger).findings}


def test_train_only_model_fit_passes(valid_train_model_ledger) -> None:
    report = validate_ledger(valid_train_model_ledger)
    assert report.status is AccessDecision.PASS
    assert report.error_count == 0


def test_train_only_scaler_fit_passes() -> None:
    train = make_slice()
    state = make_state(
        state_id="scaler-state",
        state_kind=StateKind.SCALER,
        fitted_event_id="fit-scaler",
        fitted_slice=train,
    )
    event = make_event(
        event_id="fit-scaler",
        sequence_no=1,
        operation=AccessOperation.FIT_SCALER,
        input_slices=[train],
        output_state=state,
    )
    assert validate_ledger(make_ledger([event])).status is AccessDecision.PASS


def test_validation_scaler_fit_is_blocked() -> None:
    validation = make_slice(data_role=DataRole.VALIDATION)
    state = make_state(
        state_id="scaler-state",
        state_kind=StateKind.SCALER,
        fitted_event_id="fit-scaler",
        fitted_slice=validation,
    )
    event = make_event(
        event_id="fit-scaler",
        sequence_no=1,
        operation=AccessOperation.FIT_SCALER,
        stage=Stage.VALIDATION,
        input_slices=[validation],
        output_state=state,
    )
    assert FindingCode.FIT_SCOPE_VIOLATION in codes(make_ledger([event]))


def test_holdout_model_fit_is_blocked() -> None:
    holdout = make_slice(data_role=DataRole.HOLDOUT)
    state = make_state(
        state_id="model-state",
        state_kind=StateKind.MODEL,
        fitted_event_id="fit-model",
        fitted_slice=holdout,
    )
    event = make_event(
        event_id="fit-model",
        sequence_no=1,
        operation=AccessOperation.FIT_MODEL,
        stage=Stage.HOLDOUT,
        input_slices=[holdout],
        output_state=state,
    )
    observed = codes(make_ledger([event]))
    assert FindingCode.FIT_SCOPE_VIOLATION in observed
    assert FindingCode.HOLDOUT_LEAKAGE in observed


def test_train_fitted_scaler_can_transform_validation() -> None:
    train = make_slice()
    validation = make_slice(
        dataset_id="dataset/validation",
        dataset_sha256="c" * 64,
        data_role=DataRole.VALIDATION,
        row_start=100,
        row_end=119,
        contains_targets=True,
    )
    state = make_state(
        state_id="scaler-state",
        state_kind=StateKind.SCALER,
        fitted_event_id="fit-scaler",
        fitted_slice=train,
    )
    fit = make_event(
        event_id="fit-scaler",
        sequence_no=1,
        operation=AccessOperation.FIT_SCALER,
        input_slices=[train],
        output_state=state,
    )
    transform = make_event(
        event_id="transform-validation",
        sequence_no=2,
        operation=AccessOperation.TRANSFORM,
        stage=Stage.VALIDATION,
        input_slices=[validation],
        input_states=[state],
        parents=[fit.event_id],
    )
    assert validate_ledger(make_ledger([fit, transform])).status is AccessDecision.PASS
