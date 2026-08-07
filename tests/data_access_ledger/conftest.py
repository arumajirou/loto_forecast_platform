from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from loto.data_access_ledger import (
    AccessEvent,
    AccessOperation,
    DataAccessLedger,
    DataRole,
    DatasetSlice,
    FoldRole,
    Stage,
    StateKind,
    StateReference,
    build_ledger,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)
ORIGIN = BASE + timedelta(days=100)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def make_slice(
    *,
    dataset_id: str = "dataset/train",
    dataset_sha256: str = HASH_A,
    data_role: DataRole = DataRole.TRAIN,
    row_start: int = 0,
    row_end: int = 99,
    observed_start: datetime | None = None,
    observed_end: datetime | None = None,
    available_at: datetime | None = None,
    forecast_origin: datetime = ORIGIN,
    contains_targets: bool = True,
    contains_actuals: bool = False,
    immutable_source: bool = True,
    fold_id: str | None = None,
    fold_role: FoldRole | None = None,
    draw_id: str | None = None,
) -> DatasetSlice:
    return DatasetSlice(
        dataset_id=dataset_id,
        dataset_sha256=dataset_sha256,
        data_role=data_role,
        game_id="numbers4",
        series_ids=["d1", "d2", "d3", "d4"],
        row_start=row_start,
        row_end=row_end,
        observed_time_start=observed_start or BASE,
        observed_time_end=observed_end or (BASE + timedelta(days=90)),
        available_at=available_at or (BASE + timedelta(days=91)),
        forecast_origin=forecast_origin,
        contains_targets=contains_targets,
        contains_actuals=contains_actuals,
        immutable_source=immutable_source,
        fold_id=fold_id,
        fold_role=fold_role,
        draw_id=draw_id,
    )


def make_state(
    *,
    state_id: str,
    state_kind: StateKind,
    fitted_event_id: str,
    fitted_slice: DatasetSlice,
    state_sha256: str = HASH_B,
    bound_run_id: str = "run-v1",
    fold_sha256: str | None = None,
    contains_actuals: bool = False,
) -> StateReference:
    return StateReference(
        state_id=state_id,
        state_kind=state_kind,
        state_sha256=state_sha256,
        fitted_event_id=fitted_event_id,
        fitted_dataset_sha256=fitted_slice.dataset_sha256,
        fitted_data_role=fitted_slice.data_role,
        fitted_row_start=fitted_slice.row_start,
        fitted_row_end=fitted_slice.row_end,
        bound_run_id=bound_run_id,
        fold_sha256=fold_sha256,
        contains_actuals=contains_actuals,
    )


def make_event(
    *,
    event_id: str,
    sequence_no: int,
    operation: AccessOperation,
    stage: Stage = Stage.TRAIN,
    occurred_at: datetime | None = None,
    input_slices: list[DatasetSlice] | None = None,
    input_states: list[StateReference] | None = None,
    output_state: StateReference | None = None,
    parents: list[str] | None = None,
    forecast_origin: datetime | None = ORIGIN,
    forecast_id: str | None = None,
    fold_id: str | None = None,
    seed: int | None = None,
    actuals_known: bool = False,
    run_id: str = "run-v1",
    notes: str = "",
) -> AccessEvent:
    return AccessEvent(
        event_id=event_id,
        run_id=run_id,
        sequence_no=sequence_no,
        stage=stage,
        operation=operation,
        occurred_at=occurred_at or (BASE + timedelta(hours=sequence_no)),
        actor="pytest",
        input_slices=input_slices or [],
        input_states=input_states or [],
        output_state=output_state,
        parent_event_ids=parents or [],
        forecast_origin=forecast_origin,
        forecast_id=forecast_id,
        fold_id=fold_id,
        seed=seed,
        actuals_known=actuals_known,
        notes=notes,
    )


def make_ledger(
    events: list[AccessEvent],
    *,
    run_id: str = "run-v1",
    expected_seeds: list[int] | None = None,
) -> DataAccessLedger:
    return build_ledger(
        run_id=run_id,
        created_at=BASE,
        events=events,
        expected_seeds=expected_seeds,
    )


@pytest.fixture
def valid_train_model_ledger() -> DataAccessLedger:
    train = make_slice()
    state = make_state(
        state_id="model-state",
        state_kind=StateKind.MODEL,
        fitted_event_id="fit-model",
        fitted_slice=train,
    )
    fit = make_event(
        event_id="fit-model",
        sequence_no=1,
        operation=AccessOperation.FIT_MODEL,
        input_slices=[train],
        output_state=state,
    )
    return make_ledger([fit])


def as_python(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="python")
