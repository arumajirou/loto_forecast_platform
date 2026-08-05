from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from loto.darts_campaign.protocol import GameGeometry
from loto.darts_campaign.regression_models import (
    REGRESSION_MODEL_IDENTITIES,
    RegressionCampaignConfig,
    RegressionLagContract,
    RegressionModelConfig,
    build_mlforecast_parity_payload,
    run_regression_matrix,
)


class FakeSeries:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=float)
        self.static_covariates = None

    @classmethod
    def from_series(cls, series):
        return cls(series.to_numpy(float))

    @classmethod
    def from_dataframe(cls, frame):
        return cls(frame.to_numpy(float))

    def with_static_covariates(self, frame):
        copied = FakeSeries(self._values.copy())
        copied.static_covariates = frame.copy(deep=True)
        return copied

    def values(self):
        return self._values


class BaseFakeRegression:
    def __init__(
        self,
        lags,
        output_chunk_length,
        output_chunk_shift,
        multi_models,
        use_static_covariates,
        random_state,
        **kwargs,
    ):
        self.random_state = random_state
        self.kwargs = kwargs
        self.series = None

    def fit(self, series, past_covariates=None, future_covariates=None):
        self.series = series
        return self

    def predict(
        self,
        n,
        series=None,
        past_covariates=None,
        future_covariates=None,
    ):
        source = series if series is not None else self.series
        if isinstance(source, list):
            return [FakeSeries(np.full(n, index + 1.0)) for index, _ in enumerate(source)]
        return FakeSeries(np.full(n, float(self.random_state)))


class FakeSKLearnModel(BaseFakeRegression):
    def __init__(self, model, **kwargs):
        self.model = model
        super().__init__(**kwargs)


class FailingRegression(BaseFakeRegression):
    def fit(self, series, past_covariates=None, future_covariates=None):
        raise RuntimeError("synthetic failure")


class FakeEstimator:
    pass


def geometry() -> GameGeometry:
    return GameGeometry(game_id="loto7", positions=3, min_value=1, max_value=37)


def history(rows: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": range(1, rows + 1),
            "n1": range(1, rows + 1),
            "n2": range(2, rows + 2),
            "n3": range(3, rows + 3),
        }
    )


def covariates(rows: int = 16) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": range(1, rows + 1),
            "weather": np.linspace(0.0, 1.0, rows),
            "calendar": np.arange(rows, dtype=float),
        }
    )


def lag_contract() -> RegressionLagContract:
    return RegressionLagContract(
        lags=(-3, -2, -1),
        lags_past_covariates=(-2, -1),
        lags_future_covariates=(-1, 0, 1),
        output_chunk_length=1,
        random_state=1,
    )


def campaign(layout: str = "position_local") -> RegressionCampaignConfig:
    return RegressionCampaignConfig(
        run_id="regression-test",
        models=(
            RegressionModelConfig(public_name="LinearRegressionModel"),
            RegressionModelConfig(public_name="RandomForestModel"),
            RegressionModelConfig(
                public_name="SKLearnModel",
                estimator_id="ridge-v1",
            ),
        ),
        lag_contract=lag_contract(),
        series_layout=layout,
        horizon=1,
        seed=1,
        past_covariate_columns=("weather",),
        future_covariate_columns=("calendar",),
    )


def test_regression_identity_contract_is_complete() -> None:
    assert REGRESSION_MODEL_IDENTITIES == (
        "LinearRegressionModel",
        "RandomForestModel",
        "LightGBMModel",
        "XGBModel",
        "CatBoostModel",
        "SKLearnModel",
    )


def test_lag_contract_rejects_leakage_and_invalid_quantiles() -> None:
    with pytest.raises(ValueError, match="must be negative"):
        RegressionLagContract(lags=(-1, 0), random_state=1)
    with pytest.raises(ValueError, match="explicit likelihood"):
        RegressionLagContract(lags=(-1,), quantiles=(0.1, 0.9), random_state=1)
    with pytest.raises(ValueError, match="between zero and one"):
        RegressionLagContract(
            lags=(-1,),
            likelihood="quantile",
            quantiles=(0.0, 0.5),
            random_state=1,
        )


def test_sklearn_model_requires_estimator_identity() -> None:
    with pytest.raises(ValueError, match="requires estimator_id"):
        RegressionModelConfig(public_name="SKLearnModel")


def test_local_matrix_retains_dependency_and_runtime_failures() -> None:
    source = history()
    snapshot = source.copy(deep=True)
    module = SimpleNamespace(
        LinearRegressionModel=BaseFakeRegression,
        RandomForestModel=FailingRegression,
        SKLearnModel=FakeSKLearnModel,
    )
    results = run_regression_matrix(
        campaign(),
        source,
        geometry(),
        models_module=module,
        timeseries_cls=FakeSeries,
        estimator_factories={"ridge-v1": FakeEstimator},
        past_covariates=covariates(),
        future_covariates=covariates(),
    )
    assert [item.status for item in results] == ["SUCCEEDED", "FAILED", "SUCCEEDED"]
    assert results[1].failure_class == "RUNTIME_FAILED"
    assert results[0].predictions == ((1.0,), (1.0,), (1.0,))
    pd.testing.assert_frame_equal(source, snapshot)


def test_global_sequence_uses_one_model_and_returns_each_position() -> None:
    module = SimpleNamespace(
        LinearRegressionModel=BaseFakeRegression,
        RandomForestModel=BaseFakeRegression,
        SKLearnModel=FakeSKLearnModel,
    )
    results = run_regression_matrix(
        campaign("position_global_sequence"),
        history(),
        geometry(),
        models_module=module,
        timeseries_cls=FakeSeries,
        estimator_factories={"ridge-v1": FakeEstimator},
        past_covariates=covariates(),
        future_covariates=covariates(),
    )
    assert all(item.status == "SUCCEEDED" for item in results)
    assert results[0].predictions == ((1.0,), (2.0,), (3.0,))


def test_covariate_coverage_and_target_reuse_fail_closed() -> None:
    module = SimpleNamespace(
        LinearRegressionModel=BaseFakeRegression,
        RandomForestModel=BaseFakeRegression,
        SKLearnModel=FakeSKLearnModel,
    )
    with pytest.raises(ValueError, match="coverage is insufficient"):
        run_regression_matrix(
            campaign(),
            history(),
            geometry(),
            models_module=module,
            timeseries_cls=FakeSeries,
            estimator_factories={"ridge-v1": FakeEstimator},
            past_covariates=covariates(12),
            future_covariates=covariates(12),
        )

    bad = RegressionCampaignConfig(
        run_id="bad-covariate",
        models=(RegressionModelConfig(public_name="LinearRegressionModel"),),
        lag_contract=RegressionLagContract(
            lags=(-1,),
            lags_past_covariates=(-1,),
            random_state=1,
        ),
        series_layout="position_local",
        seed=1,
        past_covariate_columns=("n1",),
    )
    leaked = history(16)
    with pytest.raises(ValueError, match="cannot be reused"):
        run_regression_matrix(
            bad,
            history(),
            geometry(),
            models_module=module,
            timeseries_cls=FakeSeries,
            past_covariates=leaked,
        )


def test_unknown_model_arguments_are_not_silently_dropped() -> None:
    config = RegressionCampaignConfig(
        run_id="unknown-argument",
        models=(
            RegressionModelConfig(
                public_name="LinearRegressionModel",
                model_args={"unknown_argument": 3},
            ),
        ),
        lag_contract=RegressionLagContract(lags=(-1,), random_state=1),
        series_layout="position_local",
        seed=1,
    )

    class StrictModel:
        def __init__(
            self,
            lags,
            output_chunk_length,
            output_chunk_shift,
            multi_models,
            use_static_covariates,
            random_state,
        ):
            pass

    results = run_regression_matrix(
        config,
        history(),
        geometry(),
        models_module=SimpleNamespace(LinearRegressionModel=StrictModel),
        timeseries_cls=FakeSeries,
    )
    assert results[0].failure_class == "INVALID_REQUEST"
    assert "unknown_argument" in (results[0].message or "")


def test_mlforecast_parity_hash_is_stable_and_sensitive() -> None:
    config = campaign()
    fold = {"strategy": "expanding_window", "horizon": 1, "step": 1}
    first = build_mlforecast_parity_payload(config, fold_contract=fold)
    second = build_mlforecast_parity_payload(config, fold_contract=fold)
    changed = build_mlforecast_parity_payload(
        config,
        fold_contract={**fold, "step": 2},
    )
    assert first["sha256"] == second["sha256"]
    assert first["sha256"] != changed["sha256"]
