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
    loaded_prediction: pd.DataFrame
    fail_save = False

    def __init__(self, prediction: pd.DataFrame) -> None:
        self.models = [FakeAutoModel()]
        self._prediction = prediction

    def save(self, path: str, **_kwargs: Any) -> None:
        if self.fail_save:
            raise RuntimeError("synthetic save failure")
        Path(path).mkdir(parents=True, exist_ok=True)

    def predict(self, **_kwargs: Any) -> pd.DataFrame:
        return self._prediction.copy()

    @classmethod
    def load(cls, _path: str) -> FakeNeuralForecast:
        return cls(cls.loaded_prediction)


def _patch_runtime_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_runtime_certification_compares_predictions_by_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_runtime_snapshots(monkeypatch)
    before = pd.DataFrame(
        {
            "unique_id": ["series-b", "series-a"],
            "ds": [2, 1],
            "candidate": [2.0, 1.0],
        }
    )
    FakeNeuralForecast.loaded_prediction = pd.DataFrame(
        {
            "unique_id": ["series-a", "series-b"],
            "ds": [1, 2],
            "candidate": [1.0, 2.0],
        }
    )

    result = certify_saved_runtime(
        neuralforecast=FakeNeuralForecast(before),
        neuralforecast_class=FakeNeuralForecast,
        model_path=tmp_path / "model" / "neuralforecast",
        prediction_before=before,
        alias="candidate",
        verbose=False,
        require_gpu=False,
    )

    assert result["status"] == "PASS"
    assert result["key_match"] is True
    assert result["prediction_match"] is True
    evidence = json.loads(
        (tmp_path / "model" / "runtime_certification.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "PASS"
    assert evidence["key_columns"] == ["unique_id", "ds"]


def test_runtime_certification_rejects_identity_mismatch_and_persists_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_runtime_snapshots(monkeypatch)
    before = pd.DataFrame(
        {
            "unique_id": ["series-a", "series-b"],
            "ds": [1, 2],
            "candidate": [1.0, 2.0],
        }
    )
    FakeNeuralForecast.loaded_prediction = pd.DataFrame(
        {
            "unique_id": ["series-a", "series-c"],
            "ds": [1, 2],
            "candidate": [1.0, 2.0],
        }
    )
    model_path = tmp_path / "model" / "neuralforecast"

    with pytest.raises(RuntimeError, match="evidence="):
        certify_saved_runtime(
            neuralforecast=FakeNeuralForecast(before),
            neuralforecast_class=FakeNeuralForecast,
            model_path=model_path,
            prediction_before=before,
            alias="candidate",
            verbose=False,
            require_gpu=False,
        )

    evidence = json.loads(
        (model_path.parent / "runtime_certification.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "FAIL"
    assert evidence["key_match"] is False
    assert "prediction_key_match" in evidence["failed_checks"]


def test_runtime_certification_persists_save_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_runtime_snapshots(monkeypatch)
    before = pd.DataFrame(
        {
            "unique_id": ["series-a"],
            "ds": [1],
            "candidate": [1.0],
        }
    )
    FakeNeuralForecast.loaded_prediction = before.copy()
    failing = FakeNeuralForecast(before)
    failing.fail_save = True
    model_path = tmp_path / "model" / "neuralforecast"

    with pytest.raises(RuntimeError, match="evidence="):
        certify_saved_runtime(
            neuralforecast=failing,
            neuralforecast_class=FakeNeuralForecast,
            model_path=model_path,
            prediction_before=before,
            alias="candidate",
            verbose=False,
            require_gpu=False,
        )

    evidence = json.loads(
        (model_path.parent / "runtime_certification.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "FAIL"
    assert evidence["failed_phase"] == "save"
    assert evidence["error_type"] == "RuntimeError"
    assert evidence["error"] == "synthetic save failure"
