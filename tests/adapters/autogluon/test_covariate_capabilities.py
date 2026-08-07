from __future__ import annotations

import pytest

from loto.adapters.autogluon.covariate_capabilities import (
    CovariateCapabilityError,
    CovariateRole,
    build_covariate_capability_decision,
    model_capability_inventory,
    requested_roles,
    validate_inventory_coverage,
)


def decide(models, configs, roles, mode="explicit_single_model"):
    return build_covariate_capability_decision(
        execution_mode=mode,
        selected_model_ids=models,
        model_hyperparameters=configs,
        roles=roles,
    )


def test_inventory_covers_all_29_models() -> None:
    validate_inventory_coverage()
    assert len(model_capability_inventory()) == 29


def test_requested_roles_are_stable() -> None:
    assert requested_roles(
        known_covariate_names=["holiday"],
        past_covariate_names=["sales"],
        static_feature_names=["position"],
    ) == (CovariateRole.KNOWN, CovariateRole.PAST, CovariateRole.STATIC)


@pytest.mark.parametrize(
    ("model_id", "roles"),
    [
        ("DirectTabular", [CovariateRole.KNOWN, CovariateRole.STATIC]),
        ("PerStepTabular", [CovariateRole.KNOWN, CovariateRole.STATIC]),
        ("RecursiveTabular", [CovariateRole.KNOWN, CovariateRole.STATIC]),
        ("DeepAR", [CovariateRole.KNOWN, CovariateRole.STATIC]),
        ("PatchTST", [CovariateRole.KNOWN]),
        (
            "TemporalFusionTransformer",
            [CovariateRole.KNOWN, CovariateRole.PAST, CovariateRole.STATIC],
        ),
        ("TiDE", [CovariateRole.KNOWN, CovariateRole.STATIC]),
        ("WaveNet", [CovariateRole.KNOWN, CovariateRole.STATIC]),
        ("Chronos2", [CovariateRole.KNOWN, CovariateRole.PAST]),
    ],
)
def test_native_routes(model_id, roles) -> None:
    decision = decide([model_id], {model_id: {}}, roles)
    assert {item.route for item in decision.model_roles} == {"native"}


def test_regressor_allows_known_and_static_for_statistical_model() -> None:
    decision = decide(
        ["Naive"],
        {"Naive": {"covariate_regressor": "GBM"}},
        [CovariateRole.KNOWN, CovariateRole.STATIC],
    )
    assert {item.route for item in decision.model_roles} == {"covariate_regressor"}


def test_regressor_does_not_allow_past_covariates() -> None:
    with pytest.raises(CovariateCapabilityError) as caught:
        decide(
            ["Naive"],
            {"Naive": {"covariate_regressor": "GBM"}},
            [CovariateRole.PAST],
        )
    assert caught.value.code == "MODEL_COVARIATE_ROLE_UNSUPPORTED"


def test_disabled_native_known_requires_regressor() -> None:
    with pytest.raises(CovariateCapabilityError):
        decide(
            ["DeepAR"],
            {"DeepAR": {"disable_known_covariates": True}},
            [CovariateRole.KNOWN],
        )
    decision = decide(
        ["DeepAR"],
        {
            "DeepAR": {
                "disable_known_covariates": True,
                "covariate_regressor": "LR",
            }
        },
        [CovariateRole.KNOWN],
    )
    assert decision.model_roles[0].route == "covariate_regressor"


def test_disabled_past_cannot_be_recovered_by_regressor() -> None:
    with pytest.raises(CovariateCapabilityError) as caught:
        decide(
            ["Chronos2"],
            {
                "Chronos2": {
                    "disable_past_covariates": True,
                    "covariate_regressor": "GBM",
                }
            },
            [CovariateRole.PAST],
        )
    assert caught.value.role == "past_covariates"


def test_multi_model_requires_every_model_to_support_every_role() -> None:
    with pytest.raises(CovariateCapabilityError) as caught:
        decide(
            ["DeepAR", "Naive"],
            {"DeepAR": {}, "Naive": {}},
            [CovariateRole.KNOWN],
            mode="explicit_multi_model",
        )
    assert caught.value.model_id == "Naive"


def test_multi_model_with_regressor_is_valid() -> None:
    decision = decide(
        ["DeepAR", "Naive"],
        {"DeepAR": {}, "Naive": {"covariate_regressor": "RF"}},
        [CovariateRole.KNOWN],
        mode="explicit_multi_model",
    )
    assert [item.route for item in decision.model_roles] == [
        "native",
        "covariate_regressor",
    ]


def test_preset_mode_is_rejected() -> None:
    with pytest.raises(CovariateCapabilityError) as caught:
        decide([], {}, [CovariateRole.KNOWN], mode="preset_automl")
    assert caught.value.code == "COVARIATES_REQUIRE_EXPLICIT_MODELS"


@pytest.mark.parametrize("value", ["AUTO", "", 1, {"__space__": "categorical"}])
def test_invalid_covariate_regressor_is_rejected(value) -> None:
    with pytest.raises(CovariateCapabilityError) as caught:
        decide(
            ["Naive"],
            {"Naive": {"covariate_regressor": value}},
            [CovariateRole.KNOWN],
        )
    assert caught.value.code == "COVARIATE_REGRESSOR_INVALID"


def test_decision_hash_is_deterministic() -> None:
    first = decide(
        ["Naive"],
        {"Naive": {"covariate_regressor": "GBM"}},
        [CovariateRole.KNOWN],
    )
    second = decide(
        ["Naive"],
        {"Naive": {"covariate_regressor": "GBM"}},
        [CovariateRole.KNOWN],
    )
    assert first.decision_sha256 == second.decision_sha256
    assert len(first.decision_sha256) == 64
