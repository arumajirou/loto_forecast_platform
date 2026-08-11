from __future__ import annotations

import pytest

from loto.models.neuralforecast_adapter import AutoModelRequest, _merge_default_config_overrides
from loto.neuralforecast.parameter_effect import (
    build_one_factor_cases,
    resolve_overlay_auto_model_plan,
)


def _request(model_name: str = "AutoDLinear", *, n_series: int | None = None) -> AutoModelRequest:
    return AutoModelRequest(
        model_name=model_name,
        h=1,
        config={},
        backend="ray",
        cpus=4,
        gpus=1,
        parallel_trials=1,
        num_samples=1,
        time_budget=60,
        precision="32-true",
        n_series=n_series,
        random_seed=1,
        search_strategy="random",
        verbose=False,
    )


def test_partial_overlay_preserves_default_search_space() -> None:
    plan = resolve_overlay_auto_model_plan(
        _request(),
        {"learning_rate": 1e-3},
    )

    assert plan.constructor_kwargs["config"] is None
    assert plan.default_config_overrides == {
        "random_seed": 1,
        "precision": "32-true",
        "learning_rate": 1e-3,
    }
    assert "partial_parameter_overlay" in plan.adjustments

    input_size_domain = object()
    merged = _merge_default_config_overrides(
        {
            "input_size": input_size_domain,
            "learning_rate": object(),
            "batch_size": object(),
        },
        plan.default_config_overrides,
    )

    assert merged["input_size"] is input_size_domain
    assert merged["learning_rate"] == 1e-3
    assert merged["random_seed"] == 1
    assert merged["precision"] == "32-true"
    assert "batch_size" in merged


def test_overlay_seed_and_precision_update_fixed_controls() -> None:
    plan = resolve_overlay_auto_model_plan(
        _request(),
        {
            "random_seed": 7,
            "precision": "64-true",
            "max_steps": 300,
        },
    )

    assert plan.config["random_seed"] == 7
    assert plan.config["precision"] == "64-true"
    assert plan.config["max_steps"] == 300
    assert plan.precision == "64-true"
    assert plan.default_config_overrides["random_seed"] == 7
    assert plan.default_config_overrides["precision"] == "64-true"
    assert plan.default_config_overrides["max_steps"] == 300


def test_multivariate_n_series_remains_constructor_control() -> None:
    plan = resolve_overlay_auto_model_plan(
        _request("AutoTSMixer", n_series=4),
        {"learning_rate": 1e-3},
    )

    assert plan.constructor_kwargs["n_series"] == 4
    assert plan.constructor_kwargs["config"] is None
    assert plan.default_config_overrides["learning_rate"] == 1e-3
    assert "n_series" not in plan.default_config_overrides

    with pytest.raises(ValueError, match="constructor-only"):
        resolve_overlay_auto_model_plan(
            _request("AutoTSMixer", n_series=4),
            {"n_series": 8},
        )


def test_one_factor_cases_change_only_target_parameter() -> None:
    cases = build_one_factor_cases(
        _request(),
        parameter="learning_rate",
        values=(1e-4, 1e-3, 1e-2),
        control_overrides={"max_steps": 300},
    )

    assert [case.value for case in cases] == [1e-4, 1e-3, 1e-2]
    assert all(case.overrides["max_steps"] == 300 for case in cases)
    assert [case.plan.default_config_overrides["learning_rate"] for case in cases] == [
        1e-4,
        1e-3,
        1e-2,
    ]
    assert all(case.plan.default_config_overrides["random_seed"] == 1 for case in cases)
    assert all(case.plan.default_config_overrides["precision"] == "32-true" for case in cases)


def test_overlay_rejects_ambiguous_fixed_config_and_unsupported_workers() -> None:
    with pytest.raises(ValueError, match="request.config to be empty"):
        resolve_overlay_auto_model_plan(
            AutoModelRequest(
                model_name="AutoDLinear",
                h=1,
                config={"input_size": 8},
                backend="ray",
            ),
            {"learning_rate": 1e-3},
        )

    with pytest.raises(ValueError, match="unsupported"):
        resolve_overlay_auto_model_plan(
            _request(),
            {"num_workers_loader": 2},
        )
