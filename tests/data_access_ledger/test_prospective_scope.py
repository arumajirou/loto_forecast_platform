from __future__ import annotations

from datetime import timedelta

from loto.data_access_ledger import (
    AccessDecision,
    AccessOperation,
    DataRole,
    FindingCode,
    Stage,
    StateKind,
    validate_ledger,
)
from tests.data_access_ledger.conftest import (
    ORIGIN,
    make_event,
    make_ledger,
    make_slice,
    make_state,
)


def codes(ledger) -> set[FindingCode]:
    return {item.code for item in validate_ledger(ledger).findings}


def prediction_chain():
    train = make_slice()
    model = make_state(
        state_id="model",
        state_kind=StateKind.MODEL,
        fitted_event_id="fit-model",
        fitted_slice=train,
    )
    fit = make_event(
        event_id="fit-model",
        sequence_no=1,
        operation=AccessOperation.FIT_MODEL,
        input_slices=[train],
        output_state=model,
    )
    features = make_slice(
        dataset_id="dataset/prospective-features",
        dataset_sha256="c" * 64,
        data_role=DataRole.PROSPECTIVE_FEATURES,
        row_start=100,
        row_end=100,
        contains_targets=False,
        draw_id="draw-101",
    )
    predict = make_event(
        event_id="predict",
        sequence_no=2,
        operation=AccessOperation.PREDICT,
        stage=Stage.PROSPECTIVE,
        input_slices=[features],
        input_states=[model],
        parents=[fit.event_id],
        forecast_id="draw-101",
    )
    lock = make_event(
        event_id="lock",
        sequence_no=3,
        operation=AccessOperation.LOCK_PREDICTION,
        stage=Stage.PROSPECTIVE,
        parents=[predict.event_id],
        forecast_id="draw-101",
    )
    actual = make_slice(
        dataset_id="dataset/actuals",
        dataset_sha256="d" * 64,
        data_role=DataRole.ACTUALS,
        row_start=100,
        row_end=100,
        observed_start=ORIGIN + timedelta(days=1),
        observed_end=ORIGIN + timedelta(days=1),
        available_at=ORIGIN + timedelta(days=1),
        forecast_origin=ORIGIN,
        contains_targets=True,
        contains_actuals=True,
        draw_id="draw-101",
    )
    read = make_event(
        event_id="read-actual",
        sequence_no=4,
        operation=AccessOperation.READ_ACTUALS,
        stage=Stage.SCORING,
        input_slices=[actual],
        parents=[lock.event_id],
        forecast_id="draw-101",
        actuals_known=True,
    )
    score = make_event(
        event_id="score",
        sequence_no=5,
        operation=AccessOperation.SCORE,
        stage=Stage.SCORING,
        input_slices=[actual],
        parents=[read.event_id],
        forecast_id="draw-101",
        actuals_known=True,
    )
    return fit, predict, lock, read, score


def test_prediction_lock_actual_score_order_passes() -> None:
    report = validate_ledger(make_ledger(list(prediction_chain())))
    assert report.status is AccessDecision.PASS


def test_actual_read_before_prediction_is_blocked() -> None:
    actual = make_slice(
        dataset_id="dataset/actuals",
        dataset_sha256="d" * 64,
        data_role=DataRole.ACTUALS,
        contains_actuals=True,
        draw_id="draw-1",
    )
    read = make_event(
        event_id="read-actual",
        sequence_no=1,
        operation=AccessOperation.READ_ACTUALS,
        stage=Stage.SCORING,
        input_slices=[actual],
        forecast_id="draw-1",
        actuals_known=True,
    )
    predict = make_event(
        event_id="predict",
        sequence_no=2,
        operation=AccessOperation.PREDICT,
        stage=Stage.PROSPECTIVE,
        forecast_id="draw-1",
    )
    observed = codes(make_ledger([read, predict]))
    assert FindingCode.PROSPECTIVE_ACTUAL_LEAKAGE in observed
    assert FindingCode.ACTUAL_READ_BEFORE_LOCK in observed


def test_actual_read_before_lock_is_blocked() -> None:
    fit, predict, _, read, _ = prediction_chain()
    read = read.model_copy(update={"sequence_no": 3, "parent_event_ids": [predict.event_id]})
    assert FindingCode.ACTUAL_READ_BEFORE_LOCK in codes(make_ledger([fit, predict, read]))


def test_score_before_actual_read_is_blocked() -> None:
    fit, predict, lock, _, score = prediction_chain()
    score = score.model_copy(update={"sequence_no": 4, "parent_event_ids": [lock.event_id]})
    assert FindingCode.SCORE_BEFORE_ACTUAL_READ in codes(make_ledger([fit, predict, lock, score]))


def test_future_available_feature_is_blocked() -> None:
    feature = make_slice(
        dataset_id="dataset/future",
        dataset_sha256="c" * 64,
        data_role=DataRole.PROSPECTIVE_FEATURES,
        available_at=ORIGIN + timedelta(seconds=1),
        forecast_origin=ORIGIN,
        contains_targets=False,
    )
    predict = make_event(
        event_id="predict",
        sequence_no=1,
        operation=AccessOperation.PREDICT,
        stage=Stage.PROSPECTIVE,
        input_slices=[feature],
        forecast_id="draw-1",
    )
    assert FindingCode.FUTURE_AVAILABILITY_VIOLATION in codes(make_ledger([predict]))


def test_actual_draw_identity_mismatch_is_blocked() -> None:
    fit, predict, lock, read, _ = prediction_chain()
    mismatched = read.input_slices[0].model_copy(update={"draw_id": "draw-999"})
    read = read.model_copy(update={"input_slices": [mismatched]})
    assert FindingCode.ACTUAL_IDENTITY_MISMATCH in codes(make_ledger([fit, predict, lock, read]))
