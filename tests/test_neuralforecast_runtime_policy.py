from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from loto.neuralforecast.runtime_certification import certify_saved_runtime


class FakeInnerModel:
    def state_dict(self) -> dict[str, np.ndarray]:
        return {"weight": np.array([1.0], dtype=float)}


class FakeAutoModel:
    def __init__(self) -> None:
        self.model = FakeInnerModel()


class SequenceNeuralForecast:
    loaded_predictions: list[pd.DataFrame]

    def __init__(self, predictions: list[pd.DataFrame]) -> None:
        self.models = [FakeAutoModel()]
        self._predictions = [prediction.copy() for prediction in predictions]
        self._index = 0

    def save(self, path: str, **_kwargs: Any) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

    def predict(self, **_kwargs: Any) -> pd.DataFrame:
        prediction = self._predictions[self._index % len(self._predictions)]
        self._index += 1
        return prediction.copy()

    @classmethod
    def load(cls, _path: str) -> SequenceNeuralForecast:
        return cls(cls.loaded_predictions)


class SingleNeuralForecast:
    loaded_prediction: pd.DataFrame

    def __init__(self, prediction: pd.DataFrame) -> None:
        self.models = [FakeAutoModel()]
        self._prediction = prediction

    def save(self, path: str, **_kwargs: Any) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

    def predict(self, **_kwargs: Any) -> pd.DataFrame:
        return self._prediction.copy()

    @classmethod
    def load(cls, _path: str) -> SingleNeuralForecast:
        return cls(cls.loaded_prediction)


def _prediction(value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_id": ["series-a"],
            "ds": [1],
            "candidate": [value],
        }
    )


def _patch_cpu_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "loto.neuralforecast.runtime_certification.torch_runtime_snapshot",
        lambda _model: {
            "parameter_device": "cpu",
            "trainer_root_device": "cpu",
            "cuda_memory_allocated": 0,
            "cuda_memory_reserved": 0,
            "cuda_peak_memory_allocated": 0,
        },
    )
    monkeypatch.setattr(
        "loto.neuralforecast.runtime_certification._safe_gpu_process_snapshot",
        lambda: {"gpu_pid_verified": False, "rows": []},
    )


def test_stochastic_policy_compares_seeded_distribution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_cpu_runtime(monkeypatch)
    before_predictions = [_prediction(value) for value in (0.0, 2.0, 4.0)]
    after_predictions = [_prediction(value) for value in (4.0, 2.0, 0.0)]
    SequenceNeuralForecast.loaded_predictions = after_predictions

    result = certify_saved_runtime(
        neuralforecast=SequenceNeuralForecast(before_predictions),
        neuralforecast_class=SequenceNeuralForecast,
        model_path=tmp_path / "model" / "neuralforecast",
        prediction_before=_prediction(9.0),
        alias="candidate",
        verbose=False,
        require_gpu=False,
        prediction_policy="stochastic",
        random_seed=7,
        stochastic_samples=3,
    )

    assert result["status"] == "PASS"
    assert result["prediction_policy"] == "stochastic"
    assert result["prediction_comparison"]["mean_match"] is True
    assert result["prediction_comparison"]["std_match"] is True
    assert result["prediction_comparison"]["seeds"] == [7, 8, 9]
    assert (tmp_path / "model" / "prediction_samples_before_save.csv").is_file()
    assert (tmp_path / "model" / "prediction_samples_after_load.csv").is_file()


def test_mixed_precision_uses_precision_specific_tolerance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_cpu_runtime(monkeypatch)
    before = _prediction(1.0)
    SingleNeuralForecast.loaded_prediction = _prediction(1.002)

    result = certify_saved_runtime(
        neuralforecast=SingleNeuralForecast(before),
        neuralforecast_class=SingleNeuralForecast,
        model_path=tmp_path / "model" / "neuralforecast",
        prediction_before=before,
        alias="candidate",
        verbose=False,
        require_gpu=False,
        precision="bf16-mixed",
    )

    assert result["status"] == "PASS"
    assert result["comparison_atol"] == pytest.approx(5e-3)


def test_post_fit_cuda_snapshot_is_not_formal_training_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prediction = _prediction(1.0)
    SingleNeuralForecast.loaded_prediction = prediction
    monkeypatch.setattr(
        "loto.neuralforecast.runtime_certification.torch_runtime_snapshot",
        lambda _model: {
            "parameter_device": "cuda:0",
            "trainer_root_device": "cuda:0",
            "cuda_memory_allocated": 1024,
            "cuda_memory_reserved": 1024,
            "cuda_peak_memory_allocated": 1024,
        },
    )
    monkeypatch.setattr(
        "loto.neuralforecast.runtime_certification._safe_gpu_process_snapshot",
        lambda: {"gpu_pid_verified": True, "rows": ["999, python, 1024"]},
    )
    model_path = tmp_path / "model" / "neuralforecast"

    with pytest.raises(RuntimeError, match="gpu_training_evidence"):
        certify_saved_runtime(
            neuralforecast=SingleNeuralForecast(prediction),
            neuralforecast_class=SingleNeuralForecast,
            model_path=model_path,
            prediction_before=prediction,
            alias="candidate",
            verbose=False,
            require_gpu=True,
        )

    evidence = json.loads(
        (model_path.parent / "runtime_certification.json").read_text(encoding="utf-8")
    )
    # A post-fit CUDA snapshot is retained as observational compatibility
    # evidence, but schema 1.3.0 requires phase-bound inference proof.
    assert evidence["cuda_training_evidence"] is True
    assert evidence["formal_cuda_training_evidence"] is False
    assert evidence["cuda_pre_save_inference_evidence"] is False
    assert evidence["cuda_reload_inference_evidence"] is False
    assert "gpu_training_evidence" in evidence["failed_checks"]
    assert "gpu_pre_save_inference_evidence" in evidence["failed_checks"]
    assert "gpu_reload_inference_evidence" in evidence["failed_checks"]
