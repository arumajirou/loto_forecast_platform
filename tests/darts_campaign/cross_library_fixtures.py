from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from loto.darts_campaign.cross_library import (
    PROVIDER_TRACKS,
    AggregateMetric,
    AlgorithmIdentity,
    BaselineResult,
    CrossLibraryCampaignConfig,
    CrossLibraryCertificationError,
    ExecutionEvidence,
    FairnessContract,
    ForecastRecord,
    MetricVector,
    ProviderExecution,
    TemporalBoundaries,
    build_cross_library_report,
    canonical_sha256,
    certify_prediction_key_parity,
    evaluate_execution,
    run_cross_library_matrix,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64


def _algorithm(
    base_library: str,
    base_model: str,
    *,
    config_hash: str,
    family: str = "statistical",
    revision: str = "1.0.0",
    estimator_id: str | None = None,
) -> AlgorithmIdentity:
    return AlgorithmIdentity(
        algorithm_family=family,
        base_library=base_library,
        base_model=base_model,
        base_revision=revision,
        estimator_id=estimator_id,
        model_config_sha256=config_hash,
    )


def _providers() -> tuple[ProviderExecution, ...]:
    nf = _algorithm(
        "neuralforecast",
        "NHITS",
        config_hash=HASH_A,
        family="torch",
        revision="3.0.2",
    )
    sf = _algorithm(
        "statsforecast",
        "AutoARIMA",
        config_hash=HASH_B,
        revision="2.0.2",
    )
    foundation = _algorithm(
        "amazon",
        "Chronos2",
        config_hash=HASH_C,
        family="foundation",
        revision="commit-abc123",
    )
    return (
        ProviderExecution(
            provider_id="darts-native-arima",
            track="darts_native",
            execution_library="darts",
            execution_version="0.46.1",
            algorithm=_algorithm(
                "darts",
                "ARIMA",
                config_hash=HASH_D,
                revision="0.46.1",
            ),
            canonical_for_algorithm=True,
            runtime="notorch",
            requested_device="cpu",
        ),
        ProviderExecution(
            provider_id="darts-nf-nhits",
            track="darts_neuralforecast_wrapper",
            execution_library="darts",
            execution_version="0.46.1",
            wrapper_library="darts",
            wrapper_version="0.46.1",
            algorithm=nf,
            canonical_for_algorithm=False,
            runtime="torch",
            requested_device="gpu",
        ),
        ProviderExecution(
            provider_id="darts-sf-autoarima",
            track="darts_statsforecast_wrapper",
            execution_library="darts",
            execution_version="0.46.1",
            wrapper_library="darts",
            wrapper_version="0.46.1",
            algorithm=sf,
            canonical_for_algorithm=False,
            runtime="notorch",
            requested_device="cpu",
        ),
        ProviderExecution(
            provider_id="nf-nhits",
            track="standalone_neuralforecast",
            execution_library="neuralforecast",
            execution_version="3.0.2",
            algorithm=nf,
            canonical_for_algorithm=True,
            runtime="torch",
            requested_device="gpu",
        ),
        ProviderExecution(
            provider_id="mlforecast-linear",
            track="standalone_mlforecast",
            execution_library="mlforecast",
            execution_version="1.0.18",
            algorithm=_algorithm(
                "sklearn",
                "LinearRegression",
                config_hash=HASH_E,
                family="regression",
                revision="1.8.0",
                estimator_id="sklearn.linear_model.LinearRegression",
            ),
            canonical_for_algorithm=True,
            runtime="notorch",
            requested_device="cpu",
        ),
        ProviderExecution(
            provider_id="sf-autoarima",
            track="standalone_statsforecast",
            execution_library="statsforecast",
            execution_version="2.0.2",
            algorithm=sf,
            canonical_for_algorithm=True,
            runtime="notorch",
            requested_device="cpu",
        ),
        ProviderExecution(
            provider_id="autogluon-chronos2",
            track="autogluon",
            execution_library="autogluon",
            execution_version="1.4.0",
            wrapper_library="autogluon",
            wrapper_version="1.4.0",
            algorithm=foundation,
            canonical_for_algorithm=False,
            runtime="torch",
            requested_device="gpu",
        ),
        ProviderExecution(
            provider_id="chronos2-direct",
            track="foundation_direct",
            execution_library="transformers",
            execution_version="5.0.0",
            algorithm=foundation,
            canonical_for_algorithm=True,
            runtime="torch",
            requested_device="gpu",
        ),
    )


def _fairness() -> FairnessContract:
    return FairnessContract(
        raw_data_sha256=HASH_A,
        comparison_data_sha256=HASH_B,
        fold_contract_sha256=HASH_C,
        feature_contract_sha256=HASH_D,
        code_contract_sha256=HASH_E,
        boundaries=TemporalBoundaries(
            train_end=100,
            validation_start=100,
            validation_end=120,
            holdout_start=120,
            holdout_end=140,
            prospective_start=140,
        ),
        positions=("N1", "N2"),
        target_columns=("N1", "N2"),
        series_layout="position_global_sequence",
        horizon=1,
        seeds=(1, 7),
        fold_ids=(0, 1),
        target_lags=(-1, -2),
        past_covariate_lags=(-1,),
        future_covariate_lags=(-1, 0),
        past_covariate_columns=("dow",),
        future_covariate_columns=("holiday",),
    )


def _config(*, parity: bool = False) -> CrossLibraryCampaignConfig:
    return CrossLibraryCampaignConfig(
        run_id="p12-test",
        providers=_providers(),
        fairness=_fairness(),
        require_wrapper_prediction_parity=parity,
        wrapper_prediction_atol=1e-12,
    )


def _records(provider_id: str, *, offset: float = 0.0) -> tuple[ForecastRecord, ...]:
    output: list[ForecastRecord] = []
    for seed in (1, 7):
        for fold_id, target in ((0, 130), (1, 131)):
            for position, actual in (("N1", 3.0), ("N2", 7.0)):
                output.append(
                    ForecastRecord(
                        provider_id=provider_id,
                        seed=seed,
                        fold_id=fold_id,
                        origin=target - 1,
                        target_index=target,
                        position=position,
                        actual=actual,
                        predicted=actual + offset,
                    )
                )
    return tuple(output)


def _evidence(
    provider: ProviderExecution,
    fairness: FairnessContract,
    *,
    offset: float = 0.0,
) -> ExecutionEvidence:
    gpu = {}
    effective = "cpu"
    if provider.requested_device == "gpu":
        effective = "gpu"
        gpu = {
            "process_pid": 100,
            "gpu_pid": 100,
            "vram_before_bytes": 10,
            "vram_peak_bytes": 20,
            "vram_after_bytes": 12,
        }
    return ExecutionEvidence(
        provider_id=provider.provider_id,
        status="SUCCESS",
        fairness_sha256=fairness.contract_sha256(),
        data_sha256=fairness.comparison_data_sha256,
        config_sha256=provider.algorithm.model_config_sha256,
        code_sha256=fairness.code_contract_sha256,
        git_commit="abcdef123456",
        package_versions={provider.execution_library: provider.execution_version},
        runtime_seconds=1.0,
        peak_memory_bytes=1024,
        requested_device=provider.requested_device,
        effective_device=effective,
        gpu_evidence=gpu,
        records=_records(provider.provider_id, offset=offset),
    )


def _aggregate(hit: float, worst: float, mae: float) -> AggregateMetric:
    mean = MetricVector(
        hit_at_plus_minus_1=hit,
        all_position_hit_at_plus_minus_1=hit,
        mae=mae,
        mse=mae * mae,
        rmse=mae,
        position_hit_at_plus_minus_1={"N1": hit, "N2": hit},
    )
    worst_vector = mean.model_copy(
        update={
            "hit_at_plus_minus_1": worst,
            "all_position_hit_at_plus_minus_1": worst,
            "position_hit_at_plus_minus_1": {"N1": worst, "N2": worst},
        }
    )
    variance = MetricVector(
        hit_at_plus_minus_1=0.0,
        all_position_hit_at_plus_minus_1=0.0,
        mae=0.0,
        mse=0.0,
        rmse=0.0,
        position_hit_at_plus_minus_1={"N1": 0.0, "N2": 0.0},
    )
    return AggregateMetric(
        mean=mean,
        variance=variance,
        worst=worst_vector,
        seed_metrics={1: mean, 7: worst_vector},
    )


def _baselines(hit: float = 0.5, worst: float = 0.4) -> tuple[BaselineResult, ...]:
    return tuple(
        BaselineResult(
            baseline_id=baseline_id,
            metrics=_aggregate(hit, worst, 2.0),
        )
        for baseline_id in (
            "random",
            "fixed",
            "mean",
            "median",
            "last",
            "frequency",
            "statistical",
        )
    )


