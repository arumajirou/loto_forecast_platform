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


class FakeNeuralForecast:
    prediction: pd.DataFrame

    def __init__(self) -> None:
        self.models = [FakeAutoModel()]

    def save(self, path: str, **_kwargs: Any) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

    def predict(self, **_kwargs: Any) -> pd.DataFrame:
        return self.prediction.copy()

    @classmethod
    def load(cls, _path: str) -> FakeNeuralForecast:
        return cls()


def test_gpu_reload_inference_requires_independent_cuda_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prediction = pd.DataFrame(
        {
            "unique_id": ["series-a"],
            "ds": [1],
            "candidate": [1.0],
        }
    )
    FakeNeuralForecast.prediction = prediction
    snapshots = iter(
        [
            {
                "parameter_device": "cuda:0",
                "trainer_root_device": "cuda:0",
                "cuda_memory_allocated": 1024,
                "cuda_memory_reserved": 1024,
                "cuda_peak_memory_allocated": 1024,
            },
            {
                "parameter_device": "cpu",
                "trainer_root_device": "cpu",
                "cuda_memory_allocated": 0,
                "cuda_memory_reserved": 0,
                "cuda_peak_memory_allocated": 0,
            },
        ]
    )
    monkeypatch.setattr(
        "loto.neuralforecast.runtime_certification.torch_runtime_snapshot",
        lambda _model: next(snapshots),
    )
    monkeypatch.setattr(
        "loto.neuralforecast.runtime_certification._safe_gpu_process_snapshot",
        lambda: {"gpu_pid_verified": False, "rows": []},
    )
    model_path = tmp_path / "model" / "neuralforecast"

    with pytest.raises(RuntimeError, match="gpu_reload_inference_evidence"):
        certify_saved_runtime(
            neuralforecast=FakeNeuralForecast(),
            neuralforecast_class=FakeNeuralForecast,
            model_path=model_path,
            prediction_before=prediction,
            alias="candidate",
            verbose=False,
            require_gpu=True,
        )

    evidence = json.loads(
        (model_path.parent / "runtime_certification.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "FAIL"
    assert evidence["cuda_training_evidence"] is True
    assert evidence["cuda_reload_inference_evidence"] is False
    assert evidence["cpu_fallback"] is True
    assert "gpu_reload_inference_evidence" in evidence["failed_checks"]
