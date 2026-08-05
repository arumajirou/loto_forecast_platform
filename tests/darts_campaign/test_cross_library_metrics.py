from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from loto.darts_campaign.cross_library import (
    PROVIDER_TRACKS,
    CrossLibraryCampaignConfig,
    CrossLibraryCertificationError,
    ExecutionEvidence,
    FairnessContract,
    ProviderExecution,
    TemporalBoundaries,
    build_cross_library_report,
    canonical_sha256,
    certify_prediction_key_parity,
    evaluate_execution,
    run_cross_library_matrix,
)
from .cross_library_fixtures import (
    HASH_A,
    HASH_B,
    HASH_E,
    _algorithm,
    _baselines,
    _config,
    _evidence,
    _fairness,
    _providers,
    _records,
)


def test_execution_metrics_include_position_all_position_and_multiseed() -> None:
    config = _config()
    provider = config.providers[0]
    result = evaluate_execution(
        provider,
        _evidence(provider, config.fairness),
        config.fairness,
    )
    assert result.metrics.mean.hit_at_plus_minus_1 == 1.0
    assert result.metrics.mean.all_position_hit_at_plus_minus_1 == 1.0
    assert result.metrics.worst.hit_at_plus_minus_1 == 1.0
    assert result.metrics.variance.hit_at_plus_minus_1 == 0.0
    assert result.metrics.mean.position_hit_at_plus_minus_1 == {
        "N1": 1.0,
        "N2": 1.0,
    }


def test_execution_rejects_duplicate_and_incomplete_position_keys() -> None:
    config = _config()
    provider = config.providers[0]
    evidence = _evidence(provider, config.fairness)
    duplicate = evidence.model_copy(
        update={"records": evidence.records + (evidence.records[0],)}
    )
    with pytest.raises(CrossLibraryCertificationError, match="duplicate forecast"):
        evaluate_execution(provider, duplicate, config.fairness)
    incomplete = evidence.model_copy(update={"records": evidence.records[:-1]})
    with pytest.raises(CrossLibraryCertificationError, match="complete position"):
        evaluate_execution(provider, incomplete, config.fairness)


def test_prediction_key_parity_rejects_provider_specific_coverage() -> None:
    config = _config()
    first = _evidence(config.providers[0], config.fairness)
    second = _evidence(config.providers[3], config.fairness)
    second = second.model_copy(update={"records": second.records[:-2]})
    with pytest.raises(CrossLibraryCertificationError, match="coverage mismatch"):
        certify_prediction_key_parity((first, second))


def test_wrapper_variants_are_compared_but_not_counted_as_algorithms() -> None:
    config = _config()
    evidence = []
    for provider in config.providers:
        offset = (
            0.1
            if provider.provider_id in {"darts-nf-nhits", "darts-sf-autoarima"}
            else 0.0
        )
        offset = 0.2 if provider.provider_id == "autogluon-chronos2" else offset
        evidence.append(_evidence(provider, config.fairness, offset=offset))
    report = build_cross_library_report(config, tuple(evidence), _baselines())
    assert report.execution_count == 8
    assert report.canonical_algorithm_count == 5
    assert len(report.wrapper_comparisons) == 3
    assert {item.variant_provider_id for item in report.wrapper_comparisons} == {
        "darts-nf-nhits",
        "darts-sf-autoarima",
        "autogluon-chronos2",
    }


def test_required_wrapper_prediction_parity_rejects_drift() -> None:
    config = _config(parity=True)
    evidence = []
    for provider in config.providers:
        offset = 0.1 if provider.provider_id == "darts-nf-nhits" else 0.0
        evidence.append(_evidence(provider, config.fairness, offset=offset))
    with pytest.raises(CrossLibraryCertificationError, match="parity failed"):
        build_cross_library_report(config, tuple(evidence), _baselines())


def test_champion_gate_uses_only_canonical_algorithms_and_all_baselines() -> None:
    config = _config()
    evidence = tuple(
        _evidence(provider, config.fairness) for provider in config.providers
    )
    report = build_cross_library_report(
        config,
        evidence,
        _baselines(hit=0.5, worst=0.4),
    )
    assert report.champion.status == "CHAMPION"
    canonical_ids = {
        provider.provider_id
        for provider in config.providers
        if provider.canonical_for_algorithm
    }
    assert report.champion.provider_id in canonical_ids
    assert report.champion.provider_id not in {
        "darts-nf-nhits",
        "darts-sf-autoarima",
        "autogluon-chronos2",
    }
    with pytest.raises(ValidationError):
        CrossLibraryCampaignConfig(
            run_id="best-seed-only",
            providers=config.providers,
            fairness=config.fairness,
            allow_best_seed_only=True,
        )
