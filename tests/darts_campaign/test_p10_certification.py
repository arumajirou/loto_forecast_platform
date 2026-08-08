from __future__ import annotations

import numpy as np
import pytest

from loto.darts_campaign.ensemble_conformal import (
    BaseModelEvidence,
    CertificationError,
    ConformalConfig,
    EnsembleConfig,
    ForecastPoint,
    P10ContractError,
    StackingEvidence,
    TemporalPartition,
    certify_conformal_quantiles,
    certify_naive_average,
    certify_stacking_evidence,
    compute_interval_metrics,
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


def test_naive_average_parity_shape_and_finite_checks() -> None:
    base = {"a": np.asarray([[1.0, 3.0], [5.0, 7.0]]), "b": np.asarray([[3.0, 5.0], [7.0, 9.0]])}
    observed = np.asarray([[2.0, 4.0], [6.0, 8.0]])
    report = certify_naive_average(base, observed, base_model_ids=("a", "b"))
    assert report["max_abs_delta"] == 0.0
    with pytest.raises(CertificationError, match="arithmetic mean"):
        certify_naive_average(base, observed + 0.1, base_model_ids=("a", "b"))
    bad = {"a": base["a"], "b": np.asarray([[np.nan, 1.0], [2.0, 3.0]])}
    with pytest.raises(CertificationError, match="NaN or Inf"):
        certify_naive_average(bad, observed, base_model_ids=("a", "b"))


def test_regression_stacking_rejects_leakage_and_incomplete_rows() -> None:
    training = tuple(
        _point(model, seed=seed, fold_id=0, origin=12, target=13, position="N1")
        for seed in (1, 7)
        for model in ("a", "b")
    )
    evaluation = tuple(
        _point("ensemble", seed=seed, fold_id=0, origin=15, target=16, position="N1")
        for seed in (1, 7)
    )
    evidence = StackingEvidence(
        training_records=training,
        evaluation_records=evaluation,
        observed_base_model_ids=("a", "b"),
        observed_seeds=(1, 7),
        observed_fold_ids=(0,),
    )
    report = certify_stacking_evidence(
        evidence,
        expected_base_model_ids=("a", "b"),
        expected_seeds=(1, 7),
        expected_fold_ids=(0,),
        partition=PARTITION,
    )
    assert report["training_record_count"] == 4
    leaking = evidence.model_copy(
        update={
            "training_records": training
            + (_point("a", seed=1, fold_id=0, origin=15, target=16, position="N1"),)
        }
    )
    with pytest.raises(CertificationError, match="evaluation-period"):
        certify_stacking_evidence(
            leaking,
            expected_base_model_ids=("a", "b"),
            expected_seeds=(1, 7),
            expected_fold_ids=(0,),
            partition=PARTITION,
        )
    incomplete = evidence.model_copy(update={"training_records": training[:-1]})
    with pytest.raises(CertificationError, match="every base model"):
        certify_stacking_evidence(
            incomplete,
            expected_base_model_ids=("a", "b"),
            expected_seeds=(1, 7),
            expected_fold_ids=(0,),
            partition=PARTITION,
        )


def test_conformal_base_requires_prefit_global_and_qr_probabilistic() -> None:
    from loto.darts_campaign.ensemble_conformal import validate_conformal_base

    naive = _conformal("ConformalNaiveModel")
    assert validate_conformal_base(naive, {"q": _base("q")}, PARTITION).model_id == "q"
    qr = _conformal("ConformalQRModel")
    with pytest.raises(P10ContractError, match="probabilistic"):
        validate_conformal_base(qr, {"q": _base("q")}, PARTITION)
    quantiles = (0.1, 0.5, 0.9)
    model = _base("q", probabilistic=True, quantiles=quantiles)
    assert validate_conformal_base(qr, {"q": model}, PARTITION).quantiles == quantiles


def test_interval_metrics_and_quantile_non_crossing() -> None:
    actual = np.asarray([[2.0, 4.0], [6.0, 8.0]])
    low = actual - 1.0
    median = actual
    high = actual + 1.0
    metric = compute_interval_metrics(actual, low, high, lower_quantile=0.1, upper_quantile=0.9)
    assert metric.empirical_coverage == 1.0
    assert metric.nominal_coverage == pytest.approx(0.8)
    cert = certify_conformal_quantiles(
        _conformal("ConformalNaiveModel"),
        PARTITION,
        actual,
        {0.1: low, 0.5: median, 0.9: high},
        base_median_prediction=median,
    )
    assert cert.non_crossing
    assert cert.median_base_parity is True
    assert cert.calibration_indices == (12, 13, 14)
    with pytest.raises(CertificationError, match="cross"):
        certify_conformal_quantiles(
            _conformal("ConformalNaiveModel"),
            PARTITION,
            actual,
            {0.1: high, 0.5: median, 0.9: low},
            base_median_prediction=median,
        )


def test_conformal_median_parity_and_shape_are_fail_closed() -> None:
    actual = np.ones((2, 2))
    predictions = {0.1: np.zeros((2, 2)), 0.5: np.ones((2, 2)), 0.9: np.full((2, 2), 2.0)}
    with pytest.raises(CertificationError, match="base median"):
        certify_conformal_quantiles(
            _conformal("ConformalNaiveModel"),
            PARTITION,
            actual,
            predictions,
            base_median_prediction=np.zeros((2, 2)),
        )
    with pytest.raises(CertificationError, match="shapes differ"):
        compute_interval_metrics(
            actual, np.zeros((1, 2)), np.ones((2, 2)), lower_quantile=0.1, upper_quantile=0.9
        )
