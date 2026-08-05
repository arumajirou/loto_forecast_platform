from __future__ import annotations

import sys
from types import ModuleType

import optuna
import pytest

from loto.models.neuralforecast_search_policy import (
    SearchBackend,
    SearchPolicyDependencyError,
    SearchPolicyError,
    SearchStrategy,
    instantiate_search_algorithm,
    resolve_search_policy,
)


def test_auto_policy_uses_random_below_threshold_and_tpe_at_threshold() -> None:
    below = resolve_search_policy(
        backend="optuna",
        strategy="auto",
        search_seed=1,
        num_samples=9,
        model_name="AutoNHITS",
    )
    at_threshold = resolve_search_policy(
        backend="optuna",
        strategy="auto",
        search_seed=1,
        num_samples=10,
        model_name="AutoNHITS",
    )

    assert below.resolved_strategy is SearchStrategy.RANDOM
    assert below.algorithm_name == "RandomSampler"
    assert at_threshold.resolved_strategy is SearchStrategy.TPE
    assert at_threshold.algorithm_name == "TPESampler"
    assert at_threshold.reason_codes == (
        "AUTO_STRATEGY",
        "BUDGET_GE_AUTO_TPE_THRESHOLD",
    )


def test_optuna_materialization_preserves_seed_and_tpe_contract() -> None:
    decision = resolve_search_policy(
        backend=SearchBackend.OPTUNA,
        strategy=SearchStrategy.TPE,
        search_seed=42,
        num_samples=30,
    )

    materialized = instantiate_search_algorithm(decision)

    assert isinstance(materialized.algorithm, optuna.samplers.TPESampler)
    assert materialized.decision.search_seed == 42
    assert materialized.decision.algorithm_kwargs == {
        "seed": 42,
        "multivariate": True,
        "group": True,
    }
    assert materialized.decision.fallback_used is False


def _install_fake_ray(monkeypatch: pytest.MonkeyPatch) -> None:
    ray = ModuleType("ray")
    tune = ModuleType("ray.tune")
    search = ModuleType("ray.tune.search")
    basic = ModuleType("ray.tune.search.basic_variant")
    optuna_search = ModuleType("ray.tune.search.optuna")

    class BasicVariantGenerator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class OptunaSearch:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    basic.BasicVariantGenerator = BasicVariantGenerator
    optuna_search.OptunaSearch = OptunaSearch
    ray.tune = tune
    tune.search = search
    search.basic_variant = basic
    search.optuna = optuna_search
    for name, module in {
        "ray": ray,
        "ray.tune": tune,
        "ray.tune.search": search,
        "ray.tune.search.basic_variant": basic,
        "ray.tune.search.optuna": optuna_search,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_ray_policy_materializes_the_resolved_searcher(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ray(monkeypatch)
    decision = resolve_search_policy(
        backend="ray",
        strategy="auto",
        search_seed=2026,
        num_samples=10,
    )

    materialized = instantiate_search_algorithm(decision)

    assert decision.algorithm_name == "OptunaSearch"
    assert materialized.algorithm.kwargs == {"seed": 2026}


def test_missing_dependency_fails_closed_unless_fallback_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = resolve_search_policy(
        backend="ray",
        strategy="random",
        search_seed=1,
        num_samples=1,
    )

    real_import = __import__

    def blocked_import(name, *args, **kwargs):
        if name.startswith("ray"):
            raise ImportError("ray intentionally blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    with pytest.raises(SearchPolicyDependencyError, match="cannot import"):
        instantiate_search_algorithm(decision)

    fallback = instantiate_search_algorithm(decision, allow_fallback=True)
    assert fallback.algorithm is None
    assert fallback.decision.fallback_used is True
    assert fallback.decision.effective_algorithm_name == "library_default"


def test_autohint_optuna_and_ray_cmaes_are_rejected() -> None:
    with pytest.raises(SearchPolicyError, match="AutoHINT"):
        resolve_search_policy(
            backend="optuna",
            strategy="auto",
            search_seed=1,
            num_samples=10,
            model_name="AutoHINT",
        )
    with pytest.raises(SearchPolicyError, match="cmaes"):
        resolve_search_policy(
            backend="ray",
            strategy="cmaes",
            search_seed=1,
            num_samples=10,
        )


def test_same_inputs_produce_the_same_serialized_decision() -> None:
    kwargs = {
        "backend": "optuna",
        "strategy": "auto",
        "search_seed": 1,
        "num_samples": 10,
        "model_name": "AutoTFT",
    }
    first = resolve_search_policy(**kwargs)
    second = resolve_search_policy(**kwargs)

    assert first.model_dump_json() == second.model_dump_json()
