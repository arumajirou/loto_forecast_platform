from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.darts_campaign.cross_library import (
    PROVIDER_TRACKS,
    CrossLibraryCampaignConfig,
    ExecutionEvidence,
    FairnessContract,
    ProviderExecution,
)

from .cross_library_fixtures import (
    HASH_A,
    HASH_B,
    HASH_E,
    _algorithm,
    _config,
    _fairness,
    _providers,
    _records,
)


def test_campaign_requires_all_eight_provider_tracks() -> None:
    config = _config()
    assert {provider.track for provider in config.providers} == set(PROVIDER_TRACKS)
    with pytest.raises(ValidationError, match="provider track mismatch"):
        CrossLibraryCampaignConfig(
            run_id="missing-track",
            providers=config.providers[:-1],
            fairness=config.fairness,
        )


def test_wrapper_and_standalone_identity_rules_are_explicit() -> None:
    with pytest.raises(ValidationError, match="NeuralForecast base"):
        ProviderExecution(
            provider_id="bad-wrapper",
            track="darts_neuralforecast_wrapper",
            execution_library="darts",
            execution_version="0.46.1",
            wrapper_library="darts",
            wrapper_version="0.46.1",
            algorithm=_algorithm("statsforecast", "NHITS", config_hash=HASH_A),
            canonical_for_algorithm=True,
            runtime="torch",
            requested_device="gpu",
        )
    with pytest.raises(ValidationError, match="standalone providers"):
        ProviderExecution(
            provider_id="bad-standalone",
            track="standalone_statsforecast",
            execution_library="statsforecast",
            execution_version="2.0.2",
            wrapper_library="darts",
            wrapper_version="0.46.1",
            algorithm=_algorithm("statsforecast", "AutoARIMA", config_hash=HASH_A),
            canonical_for_algorithm=True,
            runtime="notorch",
            requested_device="cpu",
        )


def test_unpinned_revision_and_invalid_hash_are_rejected() -> None:
    with pytest.raises(ValidationError, match="explicitly pinned"):
        _algorithm("darts", "ARIMA", config_hash=HASH_A, revision="latest")
    with pytest.raises(ValidationError, match="SHA-256"):
        _algorithm("darts", "ARIMA", config_hash="not-a-hash")


def test_fairness_contract_rejects_leakage_and_target_reuse() -> None:
    payload = _fairness().model_dump()
    payload["target_lags"] = (-1, 0)
    with pytest.raises(ValidationError, match="strictly negative"):
        FairnessContract.model_validate(payload)
    payload = _fairness().model_dump()
    payload["past_covariate_columns"] = ("N1",)
    with pytest.raises(ValidationError, match="cannot be reused"):
        FairnessContract.model_validate(payload)


def test_duplicate_algorithm_has_exactly_one_canonical_execution() -> None:
    config = _config()
    providers = list(config.providers)
    providers[1] = providers[1].model_copy(update={"canonical_for_algorithm": True})
    with pytest.raises(ValidationError, match="exactly one canonical"):
        CrossLibraryCampaignConfig(
            run_id="duplicate-canonical",
            providers=tuple(providers),
            fairness=config.fairness,
        )


def test_gpu_success_rejects_cpu_fallback_and_missing_evidence() -> None:
    provider = _providers()[1]
    with pytest.raises(ValidationError, match="CPU fallback"):
        ExecutionEvidence(
            provider_id=provider.provider_id,
            status="SUCCESS",
            fairness_sha256=_fairness().contract_sha256(),
            data_sha256=HASH_B,
            config_sha256=HASH_A,
            code_sha256=HASH_E,
            git_commit="abcdef1",
            package_versions={},
            requested_device="gpu",
            effective_device="cpu",
            records=_records(provider.provider_id),
        )
    with pytest.raises(ValidationError, match="GPU evidence is incomplete"):
        ExecutionEvidence(
            provider_id=provider.provider_id,
            status="SUCCESS",
            fairness_sha256=_fairness().contract_sha256(),
            data_sha256=HASH_B,
            config_sha256=HASH_A,
            code_sha256=HASH_E,
            git_commit="abcdef1",
            package_versions={},
            requested_device="gpu",
            effective_device="gpu",
            records=_records(provider.provider_id),
        )
