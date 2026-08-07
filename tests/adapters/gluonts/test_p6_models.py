from __future__ import annotations

import types

import pytest

from loto.adapters.gluonts.p6_models import (
    EXPECTED_ESTIMATORS,
    PROFILE_BY_NAME,
    PROFILES,
    ConstructorState,
    FormalState,
    TrainingApi,
    build_matrix,
    inspect_estimator,
    validate_registry,
)


class FlexibleEstimator:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class StrictEstimator:
    def __init__(self, prediction_length: int):
        self.prediction_length = prediction_length


def flexible_importer(module_name: str):
    module = types.ModuleType(module_name)
    profile = next(profile for profile in PROFILES if profile.module == module_name)
    setattr(module, profile.name, FlexibleEstimator)
    return module


def test_registry_covers_exactly_nine_estimators() -> None:
    validate_registry()
    assert tuple(PROFILE_BY_NAME) == EXPECTED_ESTIMATORS
    assert len(PROFILES) == 9


def test_deep_npts_uses_epochs_and_other_models_use_lightning() -> None:
    deep_npts = PROFILE_BY_NAME["DeepNPTSEstimator"]
    assert deep_npts.training_api is TrainingApi.DEEP_NPTS_EPOCHS
    assert deep_npts.smoke_defaults["epochs"] == 1
    assert "trainer_kwargs" not in deep_npts.smoke_defaults
    for profile in PROFILES[1:]:
        assert profile.training_api is TrainingApi.LIGHTNING
        assert profile.smoke_defaults["trainer_kwargs"]["max_epochs"] == 1
        assert profile.smoke_defaults["trainer_kwargs"]["accelerator"] == "cpu"


def test_all_nine_fake_estimators_can_be_constructed() -> None:
    matrix = build_matrix("compat", construct=True, importer=flexible_importer)
    assert matrix.summary[FormalState.CONSTRUCTED_ONLY.value] == 9
    assert matrix.summary[FormalState.FAILED.value] == 0
    assert all(entry.constructor_state is ConstructorState.PASS for entry in matrix.entries)


def test_missing_runtime_is_execution_pending_not_success() -> None:
    def missing_importer(module_name: str):
        raise ModuleNotFoundError(module_name)

    matrix = build_matrix("latest", construct=True, importer=missing_importer)
    assert matrix.summary[FormalState.EXECUTION_PENDING.value] == 9
    assert matrix.summary[FormalState.CONSTRUCTED_ONLY.value] == 0


def test_unknown_constructor_argument_is_rejected() -> None:
    profile = PROFILE_BY_NAME["SimpleFeedForwardEstimator"]

    def strict_importer(module_name: str):
        module = types.ModuleType(module_name)
        module.SimpleFeedForwardEstimator = StrictEstimator
        return module

    evidence = inspect_estimator(
        profile,
        "compat",
        model_arguments={"unknown_option": 1},
        importer=strict_importer,
    )
    assert evidence.formal_state is FormalState.FAILED
    assert "unknown_option" in evidence.rejected_arguments
    assert evidence.constructor_state is ConstructorState.NOT_RUN


def test_distribution_output_must_be_profile_certified() -> None:
    profile = PROFILE_BY_NAME["WaveNetEstimator"]
    evidence = inspect_estimator(
        profile,
        "compat",
        distribution_output="StudentTOutput",
        importer=flexible_importer,
    )
    assert evidence.formal_state is FormalState.FAILED
    assert "distribution_output" in evidence.rejected_arguments


def test_matrix_rejects_missing_estimator() -> None:
    matrix = build_matrix("compat", importer=flexible_importer)
    payload = matrix.model_dump(mode="json")
    payload["entries"] = payload["entries"][:-1]
    with pytest.raises(ValueError, match="all nine estimators"):
        type(matrix).model_validate(payload)
