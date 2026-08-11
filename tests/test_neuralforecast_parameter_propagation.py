from __future__ import annotations

from loto.models.neuralforecast_adapter import (
    AutoModelRequest,
    _merge_default_config_overrides,
    resolve_auto_model_plan,
)


def test_default_ray_search_space_is_preserved_while_seed_and_precision_are_fixed() -> None:
    input_domain = object()
    learning_rate_domain = object()
    merged = _merge_default_config_overrides(
        {
            "input_size": input_domain,
            "learning_rate": learning_rate_domain,
            "random_seed": object(),
        },
        {"random_seed": 1, "precision": "32-true"},
    )

    assert merged["input_size"] is input_domain
    assert merged["learning_rate"] is learning_rate_domain
    assert merged["random_seed"] == 1
    assert merged["precision"] == "32-true"


def test_default_optuna_search_callable_is_preserved_with_fixed_controls() -> None:
    def default_config(_trial):
        return {
            "input_size": 5,
            "learning_rate": 0.01,
            "random_seed": 9,
        }

    merged = _merge_default_config_overrides(
        default_config,
        {"random_seed": 1, "precision": "32-true"},
    )

    resolved = merged(object())
    assert resolved == {
        "input_size": 5,
        "learning_rate": 0.01,
        "random_seed": 1,
        "precision": "32-true",
    }


def test_cli_seed_and_precision_become_default_search_space_overrides() -> None:
    plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoDLinear",
            h=1,
            config={},
            backend="ray",
            random_seed=1,
            precision="32-true",
            num_samples=1,
            search_strategy="random",
        )
    )

    assert plan.constructor_kwargs["config"] is None
    assert plan.config["random_seed"] == 1
    assert plan.config["precision"] == "32-true"
    assert plan.default_config_overrides == {
        "random_seed": 1,
        "precision": "32-true",
    }
    assert "official_default_search_space_with_fixed_controls" in plan.adjustments


def test_explicit_model_config_has_precedence_over_generic_cli_controls() -> None:
    plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoDLinear",
            h=1,
            config={
                "input_size": 32,
                "random_seed": 42,
                "precision": "64-true",
            },
            backend="ray",
            random_seed=1,
            precision="32-true",
        )
    )

    assert plan.default_config_overrides == {}
    assert plan.constructor_kwargs["config"] == {
        "input_size": 32,
        "random_seed": 42,
        "precision": "64-true",
    }
    assert plan.config["random_seed"] == 42
    assert plan.precision == "64-true"


def test_early_stop_control_does_not_replace_official_default_search_space() -> None:
    plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoNHITS",
            h=1,
            config={},
            backend="ray",
            random_seed=1,
            precision="32-true",
            early_stop_patience_steps=5,
        )
    )

    assert plan.constructor_kwargs["config"] is None
    assert plan.default_config_overrides == {
        "random_seed": 1,
        "precision": "32-true",
        "early_stop_patience_steps": 5,
    }


def test_multiseries_n_series_does_not_collapse_default_search_space() -> None:
    plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoTSMixer",
            h=1,
            config={},
            backend="ray",
            n_series=4,
            random_seed=1,
            precision="32-true",
        )
    )

    assert plan.constructor_kwargs["n_series"] == 4
    assert plan.constructor_kwargs["config"] is None
    assert "n_series" not in plan.config
    assert plan.default_config_overrides["random_seed"] == 1
    assert plan.default_config_overrides["precision"] == "32-true"


def test_package_installs_training_evidence_facade_and_rebinds_autohint_core_route() -> None:
    from loto.neuralforecast import db_automodel as core
    from loto.neuralforecast import db_automodel_facade as facade

    assert getattr(facade, "_loto_training_evidence_installed", False) is True
    assert core._construct_auto_hint is facade._construct_auto_hint
