from pathlib import Path

import optuna

from loto.auto_campaign.contracts import CampaignConfig, SearchConfig
from loto.auto_campaign.model_factory import _artifact_kwargs, _search_materialization


def test_campaign_uses_the_shared_optuna_policy() -> None:
    config = CampaignConfig(
        data_path=Path("input.csv"),
        search=SearchConfig(
            backend="optuna",
            strategy="auto",
            num_samples=10,
            search_seed=1,
        ),
    )

    materialized = _search_materialization(
        config=config,
        backend="optuna",
        model_name="AutoNHITS",
        num_samples=10,
    )

    assert isinstance(materialized.algorithm, optuna.samplers.TPESampler)
    assert materialized.decision.algorithm_name == "TPESampler"
    assert materialized.decision.search_seed == 1


def test_constructor_artifact_persists_the_effective_search_policy() -> None:
    config = CampaignConfig(
        data_path=Path("input.csv"),
        search=SearchConfig(backend="optuna", strategy="random", search_seed=42),
    )
    materialized = _search_materialization(
        config=config,
        backend="optuna",
        model_name="AutoTFT",
        num_samples=4,
    )

    artifact = _artifact_kwargs(
        {"h": 1},
        [{"argument": "h", "status": "ACCEPTED"}],
        materialized.decision,
    )

    assert artifact["search_policy"]["requested_strategy"] == "random"
    assert artifact["search_policy"]["effective_algorithm_name"] == "RandomSampler"
    assert artifact["search_policy"]["fallback_used"] is False
