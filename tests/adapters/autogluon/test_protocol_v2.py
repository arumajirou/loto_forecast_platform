from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.autogluon.contracts import (
    ExecutionMode,
    GameGeometry,
    ProviderOperation,
    ProviderRequestV2,
)


def _geometry(positions: int = 3) -> GameGeometry:
    return GameGeometry(
        game_id=f"fixture-{positions}",
        position_columns=tuple(f"n{i}" for i in range(1, positions + 1)),
        candidate_min=0,
        candidate_max=99,
        selection_count=positions,
        horizon=1,
    )


def _history(positions: int = 3) -> tuple[dict[str, object], ...]:
    return (
        {
            "draw_no": 1,
            "draw_date": "2026-01-01",
            **{f"n{i}": i for i in range(1, positions + 1)},
        },
    )


def test_protocol_v2_rejects_schema_v1() -> None:
    with pytest.raises(ValidationError):
        ProviderRequestV2.model_validate(
            {
                "schema_version": 1,
                "provider_version": 2,
                "run_id": "run-1",
                "operation": "discover",
            }
        )


def test_protocol_v2_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProviderRequestV2.model_validate(
            {
                "run_id": "run-1",
                "operation": "discover",
                "unexpected": True,
            }
        )


def test_discover_requires_no_history_and_defaults_seed_one() -> None:
    request = ProviderRequestV2(run_id="run-1", operation=ProviderOperation.DISCOVER)
    assert request.seed == 1
    assert request.history == ()
    assert request.schema_version == 2


def test_fit_requires_geometry_history_and_artifact_dir() -> None:
    with pytest.raises(ValidationError, match="requires non-empty history"):
        ProviderRequestV2(
            run_id="run-1",
            operation=ProviderOperation.FIT_PREDICT_SAVE,
            artifact_dir="artifacts/run-1",
        )


def test_explicit_single_model_requires_exactly_one_model() -> None:
    with pytest.raises(ValidationError, match="requires exactly one model_id"):
        ProviderRequestV2(
            run_id="run-1",
            operation=ProviderOperation.FIT_PREDICT_SAVE,
            execution_mode=ExecutionMode.EXPLICIT_SINGLE_MODEL,
            model_ids=("Naive", "AutoETS"),
            artifact_dir="artifacts/run-1",
            geometry=_geometry(),
            history=_history(),
        )


def test_preset_automl_rejects_silently_ignored_model_ids() -> None:
    with pytest.raises(ValidationError, match="must not silently accept"):
        ProviderRequestV2(
            run_id="run-1",
            operation=ProviderOperation.FIT_PREDICT_SAVE,
            model_ids=("Naive",),
            artifact_dir="artifacts/run-1",
            geometry=_geometry(),
            history=_history(),
        )


def test_valid_explicit_single_model_request() -> None:
    request = ProviderRequestV2(
        run_id="run-1",
        operation=ProviderOperation.FIT_PREDICT_SAVE,
        execution_mode=ExecutionMode.EXPLICIT_SINGLE_MODEL,
        model_ids=("Naive",),
        artifact_dir="artifacts/run-1",
        geometry=_geometry(),
        history=_history(),
    )
    assert request.model_ids == ("Naive",)
    assert request.predictor.prediction_length == request.geometry.horizon
