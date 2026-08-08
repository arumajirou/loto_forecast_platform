from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import pandas as pd

import pytest

from pydantic import ValidationError

from loto.darts_campaign.ensemble_conformal import (
    BaseModelEvidence,
    CertificationError,
    ConformalConfig,
    DependencyUnavailableError,
    EnsembleConfig,
    ForecastPoint,
    P10CampaignConfig,
    P10ContractError,
    P10_MODEL_IDENTITIES,
    StackingEvidence,
    TemporalPartition,
    assert_frame_unchanged,
    build_ensemble_plan,
    canonical_sha256,
    certify_conformal_quantiles,
    certify_naive_average,
    certify_stacking_evidence,
    compute_interval_metrics,
    p10_identity_sha256,
    run_p10_matrix,
)

PARTITION = TemporalPartition(
    train_start=0,
    train_end=10,
    calibration_start=10,
    calibration_end=15,
    evaluation_start=15,
    evaluation_end=18,
)


def _base(
    model_id: str,
    *,
    global_model: bool = True,
    fitted: bool = True,
    probabilistic: bool = False,
    quantiles: tuple[float, ...] = (),
) -> BaseModelEvidence:
    return BaseModelEvidence(
        model_id=model_id,
        model_family="regression",
        is_global=global_model,
        is_fitted=fitted,
        supports_probabilistic_prediction=probabilistic,
        supports_likelihood_parameters=probabilistic,
        likelihood_id="quantile" if probabilistic else None,
        quantiles=quantiles,
        output_chunk_length=1,
    )


def _ensemble(name: str) -> EnsembleConfig:
    return EnsembleConfig(
        public_name=name,
        base_model_ids=("a", "b"),
        regression_train_n_points=5,
        regression_model_id="ridge" if name == "RegressionEnsembleModel" else None,
    )


def _conformal(name: str) -> ConformalConfig:
    return ConformalConfig(
        public_name=name, base_model_id="q", quantiles=(0.1, 0.5, 0.9), cal_length=3, cal_stride=1
    )


def _point(
    model_id: str, *, seed: int, fold_id: int, origin: int, target: int, position: str
) -> ForecastPoint:
    return ForecastPoint(
        model_id=model_id,
        seed=seed,
        fold_id=fold_id,
        origin=origin,
        target_index=target,
        position=position,
        actual=float(target),
        predicted=float(target) + 0.25,
    )


def test_identity_hash_and_campaign_require_all_models() -> None:
    assert len(P10_MODEL_IDENTITIES) == 4
    assert p10_identity_sha256() == p10_identity_sha256()
    config = P10CampaignConfig(
        partition=PARTITION,
        ensembles=(_ensemble("NaiveEnsembleModel"), _ensemble("RegressionEnsembleModel")),
        conformal_models=(_conformal("ConformalNaiveModel"), _conformal("ConformalQRModel")),
    )
    assert config.outer_workers == 8
    with pytest.raises(ValidationError):
        P10CampaignConfig(
            partition=PARTITION,
            ensembles=(_ensemble("NaiveEnsembleModel"),),
            conformal_models=(_conformal("ConformalNaiveModel"), _conformal("ConformalQRModel")),
        )


def test_temporal_partition_and_quantile_contracts_fail_closed() -> None:
    with pytest.raises(ValidationError):
        TemporalPartition(
            train_end=10,
            calibration_start=9,
            calibration_end=12,
            evaluation_start=12,
            evaluation_end=14,
        )
    with pytest.raises(ValidationError):
        ConformalConfig(
            public_name="ConformalNaiveModel", base_model_id="a", quantiles=(0.1, 0.5, 0.8)
        )
    with pytest.raises(ValidationError):
        ConformalConfig(
            public_name="ConformalNaiveModel",
            base_model_id="a",
            quantiles=(0.1, 0.5, 0.9),
            num_samples=10,
            predict_likelihood_parameters=True,
        )


def test_ensemble_plan_prefit_global_and_shift_contracts() -> None:
    evidence = {"a": _base("a"), "b": _base("b")}
    config = _ensemble("NaiveEnsembleModel").model_copy(update={"train_forecasting_models": False})
    plan = build_ensemble_plan(config, evidence)
    assert plan.all_global and plan.all_prefitted
    bad = {"a": _base("a"), "b": _base("b", global_model=False)}
    with pytest.raises(P10ContractError):
        build_ensemble_plan(config, bad)
    shifted = {"a": _base("a"), "b": _base("b").model_copy(update={"output_chunk_shift": 1})}
    with pytest.raises(P10ContractError):
        build_ensemble_plan(_ensemble("NaiveEnsembleModel"), shifted)


def test_unavailable_base_is_retained_as_dependency_failure() -> None:
    unavailable = BaseModelEvidence(
        model_id="b",
        model_family="torch",
        available=False,
        failure_class="ImportError",
        failure_message="optional dependency missing",
    )
    with pytest.raises(DependencyUnavailableError, match="unavailable base models"):
        build_ensemble_plan(_ensemble("NaiveEnsembleModel"), {"a": _base("a"), "b": unavailable})


def test_no_silent_drop_argument_ledger_is_scoped() -> None:

    class RuntimeModel:
        def __init__(self, alpha: float = 1.0) -> None:
            self.alpha = alpha

        def fit(self, series: object, verbose: bool = False) -> None:
            del series, verbose

        def predict(self, n: int, num_samples: int = 1) -> None:
            del n, num_samples

    config = _ensemble("NaiveEnsembleModel").model_copy(
        update={
            "constructor_args": {"alpha": 2.0},
            "fit_args": {"verbose": True},
            "predict_args": {"num_samples": 1},
        }
    )
    plan = build_ensemble_plan(
        config,
        {"a": _base("a"), "b": _base("b")},
        constructor=RuntimeModel,
        fit_method=RuntimeModel.fit,
        predict_method=RuntimeModel.predict,
    )
    assert {(item.phase, item.argument) for item in plan.argument_ledger} == {
        ("constructor", "alpha"),
        ("fit", "verbose"),
        ("predict", "num_samples"),
    }
    bad = config.model_copy(update={"predict_args": {"unknown": 1}})
    with pytest.raises(P10ContractError, match="rejected predict arguments"):
        build_ensemble_plan(
            bad, {"a": _base("a"), "b": _base("b")}, predict_method=RuntimeModel.predict
        )
