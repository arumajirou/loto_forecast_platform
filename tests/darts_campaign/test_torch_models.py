from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from loto.darts_campaign.protocol import GameGeometry
from loto.darts_campaign.torch_models import (
    TORCH_MODEL_IDENTITIES,
    TorchCampaignConfig,
    TorchDeviceContract,
    TorchModelConfig,
    TorchParallelPolicy,
    TorchRuntimeObservation,
    TorchTrainingContract,
    build_parallel_plan,
    certify_device_use,
    run_torch_matrix,
)


class FakeSeries:
    def __init__(self, values: np.ndarray) -> None:
        self.data = np.asarray(values, dtype=float)

    @classmethod
    def from_series(cls, series: pd.Series) -> FakeSeries:
        return cls(series.to_numpy(float))


class FakePrediction:
    def __init__(self, values: list[float]) -> None:
        self._values = np.asarray(values, dtype=float)

    def values(self) -> np.ndarray:
        return self._values


class FakeTorchModel:
    supports_multivariate = True
    supports_probabilistic_prediction = False
    supports_past_covariates = True
    supports_future_covariates = True
    supports_static_covariates = True
    supports_sample_weight = True
    supports_transferable_series_prediction = True

    def __init__(
        self,
        input_chunk_length: int,
        output_chunk_length: int,
        output_chunk_shift: int,
        n_epochs: int,
        batch_size: int,
        optimizer_kwargs: dict[str, object],
        random_state: int,
        pl_trainer_kwargs: dict[str, object],
        save_checkpoints: bool,
        force_reset: bool,
        **kwargs: object,
    ) -> None:
        self.input_chunk_length = input_chunk_length
        self.output_chunk_length = output_chunk_length
        self.output_chunk_shift = output_chunk_shift
        self.n_epochs = n_epochs
        self.batch_size = batch_size
        self.optimizer_kwargs = optimizer_kwargs
        self.random_state = random_state
        self.pl_trainer_kwargs = pl_trainer_kwargs
        self.save_checkpoints = save_checkpoints
        self.force_reset = force_reset
        self.kwargs = kwargs
        self.series: object | None = None

    def fit(self, series: object, **kwargs: object) -> FakeTorchModel:
        self.series = series
        self.fit_kwargs = kwargs
        return self

    def predict(
        self,
        n: int,
        series: list[FakeSeries] | None = None,
        **kwargs: object,
    ) -> FakePrediction | list[FakePrediction]:
        self.predict_kwargs = kwargs
        if series is not None:
            return [FakePrediction([float(item.data[-1])] * n) for item in series]
        assert isinstance(self.series, FakeSeries)
        return FakePrediction([float(self.series.data[-1])] * n)


class NonFiniteTorchModel(FakeTorchModel):
    def predict(
        self,
        n: int,
        series: list[FakeSeries] | None = None,
        **kwargs: object,
    ) -> FakePrediction | list[FakePrediction]:
        if series is not None:
            return [FakePrediction([float("nan")] * n) for _ in series]
        return FakePrediction([float("nan")] * n)


def _geometry() -> GameGeometry:
    return GameGeometry(
        game_id="numbers3",
        positions=2,
        min_value=0,
        max_value=9,
        draw_no_col="draw_no",
        position_prefix="N",
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": list(range(1, 13)),
            "N1": [1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 1, 2],
            "N2": [2, 3, 4, 5, 6, 7, 8, 9, 0, 1, 2, 3],
        }
    )


def _models_module(**overrides: type[FakeTorchModel]) -> SimpleNamespace:
    payload = {name: FakeTorchModel for name in TORCH_MODEL_IDENTITIES}
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _gpu_observation() -> TorchRuntimeObservation:
    return TorchRuntimeObservation(
        torch_cuda_available=True,
        requested_accelerator="gpu",
        effective_accelerator="gpu",
        model_parameter_devices=("cuda:0",),
        prediction_device="cuda:0",
        process_pid=1200,
        gpu_pid=1200,
        device_index=0,
        vram_before_bytes=100,
        vram_peak_bytes=300,
        vram_after_bytes=200,
        cuda_allocated_bytes=150,
        cuda_reserved_bytes=250,
    )


def _cpu_fallback_observation() -> TorchRuntimeObservation:
    return TorchRuntimeObservation(
        torch_cuda_available=True,
        requested_accelerator="gpu",
        effective_accelerator="cpu",
        model_parameter_devices=("cpu",),
        prediction_device="cpu",
        process_pid=1200,
        cpu_fallback_reason="trainer selected CPU",
    )


def _config(
    *,
    names: tuple[str, ...] = TORCH_MODEL_IDENTITIES,
    layout: str = "position_local",
) -> TorchCampaignConfig:
    return TorchCampaignConfig(
        run_id="p7-torch-contract",
        models=tuple(TorchModelConfig(public_name=name) for name in names),
        training=TorchTrainingContract(
            input_chunk_length=4,
            output_chunk_length=1,
            n_epochs=1,
            batch_size=4,
        ),
        device=TorchDeviceContract(),
        parallel=TorchParallelPolicy(),
        series_layout=layout,
        horizon=1,
    )


def test_exact_p7_model_identities() -> None:
    assert TORCH_MODEL_IDENTITIES == (
        "NBEATSModel",
        "NHiTSModel",
        "TCNModel",
        "TFTModel",
        "DLinearModel",
        "NLinearModel",
        "TiDEModel",
        "TSMixerModel",
        "TransformerModel",
        "RNNModel",
    )


def test_parallel_and_device_contracts_fail_closed() -> None:
    assert build_parallel_plan(TorchParallelPolicy()) == {
        "outer_workers": 8,
        "max_gpu_jobs": 1,
        "max_cpu_jobs": 7,
        "gpu_queue_serialized": True,
    }
    with pytest.raises(ValueError, match="max_gpu_jobs=1"):
        TorchParallelPolicy(max_gpu_jobs=2, max_cpu_jobs=6)
    with pytest.raises(ValueError, match="exactly one device"):
        TorchDeviceContract(devices=(0, 1))
    with pytest.raises(ValueError, match="must not declare CUDA devices"):
        TorchDeviceContract(requested_accelerator="cpu", devices=(0,))


def test_constructor_contains_explicit_lightning_gpu_request() -> None:
    training = TorchTrainingContract(input_chunk_length=8, output_chunk_length=2)
    payload = training.constructor_args(TorchDeviceContract())
    assert payload["pl_trainer_kwargs"] == {"accelerator": "gpu", "devices": [0]}
    assert payload["random_state"] == 1
    assert payload["save_checkpoints"] is True
    assert payload["force_reset"] is True


def test_device_certification_requires_pid_vram_and_cuda_devices() -> None:
    passed = certify_device_use(TorchDeviceContract(), _gpu_observation())
    assert passed["status"] == "GPU_REQUESTED_AND_USED"
    assert passed["passed"] is True

    missing_pid = _gpu_observation().model_copy(update={"gpu_pid": None})
    failed = certify_device_use(TorchDeviceContract(), missing_pid)
    assert failed["failure_class"] == "GPU_PID_MISSING"
    assert failed["passed"] is False


def test_position_local_matrix_runs_all_ten_models_and_preserves_input() -> None:
    frame = _frame()
    original = frame.copy(deep=True)

    results = run_torch_matrix(
        _config(),
        frame,
        _geometry(),
        models_module=_models_module(),
        timeseries_cls=FakeSeries,
        runtime_probe=lambda *_: _gpu_observation(),
    )

    assert [item.model_name for item in results] == list(TORCH_MODEL_IDENTITIES)
    assert all(item.status == "SUCCEEDED" for item in results)
    assert all(len(item.predictions or ()) == 2 for item in results)
    assert all(
        certification["status"] == "GPU_REQUESTED_AND_USED"
        for item in results
        for certification in item.device_certifications
    )
    pd.testing.assert_frame_equal(frame, original)


def test_global_sequence_uses_one_model_for_all_positions() -> None:
    results = run_torch_matrix(
        _config(names=("NBEATSModel",), layout="position_global_sequence"),
        _frame(),
        _geometry(),
        models_module=_models_module(),
        timeseries_cls=FakeSeries,
        runtime_probe=lambda *_: _gpu_observation(),
    )
    assert results[0].status == "SUCCEEDED"
    assert results[0].predictions == ((2.0,), (3.0,))
    assert len(results[0].device_certifications) == 1


def test_cpu_fallback_is_rejected_and_does_not_stop_other_models() -> None:
    def probe(name: str, *_: object) -> TorchRuntimeObservation:
        if name == "NBEATSModel":
            return _cpu_fallback_observation()
        return _gpu_observation()

    results = run_torch_matrix(
        _config(names=("NBEATSModel", "NHiTSModel")),
        _frame(),
        _geometry(),
        models_module=_models_module(),
        timeseries_cls=FakeSeries,
        runtime_probe=probe,
    )
    assert results[0].status == "FAILED"
    assert results[0].failure_class == "CPU_FALLBACK_REJECTED"
    assert results[0].device_certifications[0]["status"] == ("GPU_REQUESTED_BUT_CPU_FALLBACK")
    assert results[1].status == "SUCCEEDED"


def test_missing_dependency_and_nonfinite_predictions_are_retained() -> None:
    module = _models_module(TCNModel=NonFiniteTorchModel)
    delattr(module, "NHiTSModel")
    results = run_torch_matrix(
        _config(names=("NHiTSModel", "TCNModel", "TFTModel")),
        _frame(),
        _geometry(),
        models_module=module,
        timeseries_cls=FakeSeries,
        runtime_probe=lambda *_: _gpu_observation(),
    )
    assert results[0].failure_class == "DEPENDENCY_MISSING"
    assert results[1].failure_class == "INVALID_REQUEST"
    assert "NaN or Inf" in (results[1].message or "")
    assert results[2].status == "SUCCEEDED"


def test_unknown_model_argument_and_short_history_fail_without_silent_drop() -> None:
    strict_class = type(
        "StrictModel",
        (FakeTorchModel,),
        {
            "__init__": lambda self, input_chunk_length: setattr(
                self, "input_chunk_length", input_chunk_length
            )
        },
    )
    config = _config(names=("NBEATSModel",))
    result = run_torch_matrix(
        config,
        _frame(),
        _geometry(),
        models_module=SimpleNamespace(NBEATSModel=strict_class),
        timeseries_cls=FakeSeries,
        runtime_probe=lambda *_: _gpu_observation(),
    )[0]
    assert result.failure_class == "INVALID_REQUEST"
    assert "rejected arguments" in (result.message or "")

    short = _frame().iloc[:4].copy()
    with pytest.raises(ValueError, match="shorter than input chunk plus horizon"):
        run_torch_matrix(
            config,
            short,
            _geometry(),
            models_module=_models_module(),
            timeseries_cls=FakeSeries,
            runtime_probe=lambda *_: _gpu_observation(),
        )


def test_runtime_object_ids_require_explicit_resolver() -> None:
    training = TorchTrainingContract(
        input_chunk_length=4,
        output_chunk_length=1,
        likelihood_id="quantile-regression",
        torch_metrics=("mae",),
    )
    with pytest.raises(ValueError, match="runtime object resolver"):
        training.constructor_args(TorchDeviceContract())

    resolved = training.constructor_args(
        TorchDeviceContract(),
        resolver=lambda kind, identity: f"{kind}:{identity}",
    )
    assert resolved["likelihood"] == "likelihood:quantile-regression"
    assert resolved["torch_metrics"] == ["torch_metric:mae"]
