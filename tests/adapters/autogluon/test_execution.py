from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.autogluon.contracts import (
    ExecutionMode,
    FitConfig,
    GameGeometry,
    PredictorConfig,
    ProviderOperation,
    ProviderRequestV2,
)
from loto.adapters.autogluon.execution import ExecutionPlanError, build_execution_plan


def _request(**overrides) -> ProviderRequestV2:
    payload = {
        "run_id": "p4-test",
        "operation": ProviderOperation.FIT_PREDICT_SAVE,
        "execution_mode": ExecutionMode.PRESET_AUTOML,
        "artifact_dir": "/tmp/p4-test",
        "history": (
            {
                "draw_no": 1,
                "draw_date": "2026-01-01",
                "n1": 1,
                "n2": 2,
                "n3": 3,
            },
        ),
        "geometry": GameGeometry(
            game_id="numbers3",
            position_columns=("n1", "n2", "n3"),
            candidate_min=0,
            candidate_max=9,
            selection_count=3,
            sort_policy="preserve",
        ),
        "predictor": PredictorConfig(prediction_length=1),
        "seed": 1,
    }
    payload.update(overrides)
    return ProviderRequestV2.model_validate(payload)


def test_preset_plan_preserves_preset_and_has_no_hidden_model_ids() -> None:
    plan = build_execution_plan(_request())
    assert plan.execution_mode == "preset_automl"
    assert plan.selected_model_ids == ()
    assert plan.fit_kwargs["presets"] == "fast_training"
    assert "hyperparameters" not in plan.fit_kwargs
    assert plan.fit_kwargs["random_seed"] == 1
    assert len(plan.plan_sha256) == 64


def test_explicit_single_maps_model_id_and_disables_preset_and_ensemble() -> None:
    request = _request(
        execution_mode=ExecutionMode.EXPLICIT_SINGLE_MODEL,
        model_ids=("Naive",),
        fit=FitConfig(hyperparameters={"seasonal_period": 1}),
    )
    plan = build_execution_plan(request)
    assert plan.fit_kwargs["hyperparameters"] == {"Naive": {"seasonal_period": 1}}
    assert "presets" not in plan.fit_kwargs
    assert plan.fit_kwargs["enable_ensemble"] is False
    transformed = {
        entry.argument: entry.status.value for entry in plan.argument_ledger
    }
    assert transformed["fit.hyperparameters"] == "TRANSFORMED"
    assert transformed["fit.presets"] == "DROPPED_WITH_REASON"
    assert transformed["fit.enable_ensemble"] == "TRANSFORMED"


def test_explicit_multi_requires_model_keyed_configuration() -> None:
    request = _request(
        execution_mode=ExecutionMode.EXPLICIT_MULTI_MODEL,
        model_ids=("Naive", "Theta"),
        fit=FitConfig(hyperparameters={"Naive": {}, "Theta": {"seasonal_period": 1}}),
    )
    plan = build_execution_plan(request)
    assert plan.fit_kwargs["hyperparameters"] == {
        "Naive": {},
        "Theta": {"seasonal_period": 1},
    }
    assert plan.fit_kwargs["enable_ensemble"] is True


def test_explicit_multi_rejects_unkeyed_configuration() -> None:
    request = _request(
        execution_mode=ExecutionMode.EXPLICIT_MULTI_MODEL,
        model_ids=("Naive", "Theta"),
        fit=FitConfig(hyperparameters={"seasonal_period": 1}),
    )
    with pytest.raises(ExecutionPlanError, match="must be keyed") as captured:
        build_execution_plan(request)
    assert captured.value.code == "MULTI_MODEL_CONFIG_REQUIRES_MODEL_KEYS"


def test_hpo_requires_tune_configuration() -> None:
    request = _request(
        execution_mode=ExecutionMode.HPO_SINGLE_MODEL,
        model_ids=("DeepAR",),
        fit=FitConfig(hyperparameters={}),
    )
    with pytest.raises(ExecutionPlanError, match="requires hyperparameter_tune_kwargs") as captured:
        build_execution_plan(request)
    assert captured.value.code == "HPO_CONFIGURATION_REQUIRED"


def test_hpo_maps_model_and_tune_configuration() -> None:
    tune = {"num_trials": 2, "scheduler": "local"}
    request = _request(
        execution_mode=ExecutionMode.HPO_SINGLE_MODEL,
        model_ids=("DeepAR",),
        fit=FitConfig(hyperparameters={}, hyperparameter_tune_kwargs=tune),
    )
    plan = build_execution_plan(request)
    assert plan.fit_kwargs["hyperparameters"] == {"DeepAR": {}}
    assert plan.fit_kwargs["hyperparameter_tune_kwargs"] == tune
    assert plan.fit_kwargs["enable_ensemble"] is False


def test_unknown_model_id_fails_closed() -> None:
    request = _request(
        execution_mode=ExecutionMode.EXPLICIT_SINGLE_MODEL,
        model_ids=("NotARealModel",),
    )
    with pytest.raises(ExecutionPlanError, match="not declared") as captured:
        build_execution_plan(request)
    assert captured.value.code == "UNKNOWN_MODEL_ID"


def test_foundation_execution_modes_are_explicitly_deferred() -> None:
    request = _request(
        execution_mode=ExecutionMode.ZERO_SHOT_FOUNDATION,
        model_ids=("Chronos2",),
    )
    with pytest.raises(ExecutionPlanError, match="deferred") as captured:
        build_execution_plan(request)
    assert captured.value.code == "EXECUTION_MODE_NOT_IMPLEMENTED_P4"


def test_duplicate_model_ids_are_rejected_by_contract() -> None:
    with pytest.raises(ValidationError, match="model_ids must be unique"):
        _request(
            execution_mode=ExecutionMode.EXPLICIT_MULTI_MODEL,
            model_ids=("Naive", "Naive"),
        )


def test_preset_mode_rejects_dictionary_hyperparameters() -> None:
    request = _request(fit=FitConfig(hyperparameters={"Naive": {}}))
    with pytest.raises(ExecutionPlanError, match="explicit model execution mode") as captured:
        build_execution_plan(request)
    assert captured.value.code == "PRESET_MODE_EXPLICIT_HYPERPARAMETERS"


def test_single_model_rejects_ensemble_configuration() -> None:
    request = _request(
        execution_mode=ExecutionMode.EXPLICIT_SINGLE_MODEL,
        model_ids=("Naive",),
        fit=FitConfig(ensemble_hyperparameters={"name": "Greedy"}),
    )
    with pytest.raises(ExecutionPlanError, match="cannot accept") as captured:
        build_execution_plan(request)
    assert captured.value.code == "ENSEMBLE_CONFIG_CONFLICT_WITH_SINGLE_MODEL"


def test_execution_plan_hash_is_deterministic() -> None:
    request = _request(
        execution_mode=ExecutionMode.EXPLICIT_SINGLE_MODEL,
        model_ids=("Naive",),
    )
    first = build_execution_plan(request).plan_sha256
    second = build_execution_plan(request).plan_sha256
    assert first == second
