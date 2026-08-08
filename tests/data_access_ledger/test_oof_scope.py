from __future__ import annotations

from datetime import timedelta

from loto.data_access_ledger import (
    AccessDecision,
    AccessOperation,
    DataRole,
    FindingCode,
    FoldRole,
    Stage,
    StateKind,
    sha256_hex,
    validate_ledger,
)
from tests.data_access_ledger.conftest import BASE, make_event, make_ledger, make_slice, make_state


def fold_hash(slices) -> str:
    return sha256_hex(
        [
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
    )


def test_chronological_tune_with_fold_hash_passes() -> None:
    train = make_slice(
        dataset_id="dataset/tune",
        fold_id="inner-1",
        fold_role=FoldRole.TRAIN,
        observed_end=BASE + timedelta(days=50),
    )
    validation = make_slice(
        dataset_id="dataset/tune-validation",
        dataset_sha256="c" * 64,
        data_role=DataRole.TRAIN,
        row_start=50,
        row_end=59,
        fold_id="inner-1",
        fold_role=FoldRole.VALIDATION,
        observed_start=BASE + timedelta(days=51),
        observed_end=BASE + timedelta(days=60),
    )
    slices = [train, validation]
    state = make_state(
        state_id="hpo-result",
        state_kind=StateKind.HPO_RESULT,
        fitted_event_id="tune",
        fitted_slice=train,
        fold_sha256=fold_hash(slices),
    )
    tune = make_event(
        event_id="tune",
        sequence_no=1,
        operation=AccessOperation.TUNE,
        input_slices=slices,
        output_state=state,
    )
    assert validate_ledger(make_ledger([tune])).status is AccessDecision.PASS


def test_tune_rejects_non_train_outer_role() -> None:
    holdout = make_slice(
        data_role=DataRole.HOLDOUT,
        fold_id="inner-1",
        fold_role=FoldRole.TRAIN,
    )
    tune = make_event(
        event_id="tune",
        sequence_no=1,
        operation=AccessOperation.TUNE,
        input_slices=[holdout],
    )
    codes = {item.code for item in validate_ledger(make_ledger([tune])).findings}
    assert FindingCode.TUNE_SCOPE_VIOLATION in codes
    assert FindingCode.HOLDOUT_LEAKAGE in codes


def test_oof_missing_seed_is_reported_as_warning() -> None:
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
        fold_id="fold-1",
        seed=42,
    )
    report = validate_ledger(make_ledger([fit, predict], expected_seeds=[42, 43]))
    assert report.status is AccessDecision.PASS
    assert report.warning_count == 1
    assert report.findings[0].code is FindingCode.OOF_SEED_MISSING
