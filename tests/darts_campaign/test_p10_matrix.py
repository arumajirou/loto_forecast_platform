from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import pandas as pd

import pytest

from pydantic import ValidationError

from loto.darts_campaign.ensemble_conformal import BaseModelEvidence, CertificationError, \
    ConformalConfig, DependencyUnavailableError, EnsembleConfig, ForecastPoint, \
    P10CampaignConfig, P10ContractError, P10_MODEL_IDENTITIES, StackingEvidence, \
    TemporalPartition, assert_frame_unchanged, build_ensemble_plan, canonical_sha256, \
    certify_conformal_quantiles, certify_naive_average, certify_stacking_evidence, \
    compute_interval_metrics, p10_identity_sha256, run_p10_matrix

PARTITION = TemporalPartition(train_start=0, train_end=10, calibration_start=10,
    calibration_end=15, evaluation_start=15, evaluation_end=18)

def _base(model_id: str, *, global_model: bool=True, fitted: bool=True, probabilistic: bool=False,
    quantiles: tuple[float, ...]=()) -> BaseModelEvidence:
    return BaseModelEvidence(model_id=model_id, model_family='regression',
        is_global=global_model, is_fitted=fitted,
        supports_probabilistic_prediction=probabilistic,
        supports_likelihood_parameters=probabilistic, likelihood_id='quantile' if probabilistic
        else None, quantiles=quantiles, output_chunk_length=1)

def _ensemble(name: str) -> EnsembleConfig:
    return EnsembleConfig(public_name=name, base_model_ids=('a', 'b'),
        regression_train_n_points=5, regression_model_id='ridge'
        if name == 'RegressionEnsembleModel' else None)

def _conformal(name: str) -> ConformalConfig:
    return ConformalConfig(public_name=name, base_model_id='q', quantiles=(0.1, 0.5, 0.9),
        cal_length=3, cal_stride=1)

def _point(model_id: str, *, seed: int, fold_id: int, origin: int, target: int,
    position: str) -> ForecastPoint:
    return ForecastPoint(model_id=model_id, seed=seed, fold_id=fold_id, origin=origin,
        target_index=target, position=position, actual=float(target), predicted=float(target)
        + 0.25)

def test_matrix_retains_all_failures_without_stopping() -> None:
    config = P10CampaignConfig(partition=PARTITION,
        ensembles=(_ensemble('NaiveEnsembleModel'), _ensemble('RegressionEnsembleModel')),
        conformal_models=(_conformal('ConformalNaiveModel'), _conformal('ConformalQRModel')),
        seeds=(1, 7), fold_ids=(0, 1))

    @dataclass
    class Runtime:

        def execute(self, task: object) -> dict[str, object]:
            if getattr(task, 'public_name') == 'RegressionEnsembleModel':
                raise RuntimeError('regressor unavailable')
            return {'task': getattr(task, 'public_name')}
    results = run_p10_matrix(config, Runtime())
    assert len(results) == 16
    failed = [item for item in results if item.status == 'FAILED']
    assert len(failed) == 4
    assert {item.task.public_name for item in failed} == {'RegressionEnsembleModel'}
    assert all((item.failure_class == 'RuntimeError' for item in failed))

def test_hash_tamper_sensitivity_and_raw_frame_immutability() -> None:
    payload = {'models': list(P10_MODEL_IDENTITIES), 'seeds': [1, 7, 19]}
    assert canonical_sha256(payload) == canonical_sha256(payload)
    changed = {'models': list(P10_MODEL_IDENTITIES), 'seeds': [1, 7, 20]}
    assert canonical_sha256(payload) != canonical_sha256(changed)
    frame = pd.DataFrame({'N1': [1, 2], 'N2': [3, 4]})
    before = frame.copy(deep=True)
    assert_frame_unchanged(before, frame)
    frame.loc[0, 'N1'] = 99
    with pytest.raises(AssertionError):
        assert_frame_unchanged(before, frame)
