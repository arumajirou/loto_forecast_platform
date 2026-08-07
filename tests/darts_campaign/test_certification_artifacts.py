from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from loto.darts_campaign.artifacts import (
    finalize_manifest,
    seal_predictions,
    verify_prediction_seal,
    write_json,
)
from loto.darts_campaign.certification import certify_model_roundtrip


class Prediction:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=float)

    def values(self):
        return self._values


class FakeModel:
    def __init__(self, value: float):
        self.value = value

    def save(self, path: str) -> None:
        Path(path).write_text(str(self.value), encoding="utf-8")

    @classmethod
    def load(cls, path: str):
        return cls(float(Path(path).read_text(encoding="utf-8")))

    def predict(self, horizon: int, **kwargs):
        return Prediction([self.value] * horizon)


def test_roundtrip_seal_and_manifest(tmp_path) -> None:
    model = FakeModel(3.0)
    result = certify_model_roundtrip(
        model=model,
        initial_prediction=model.predict(2),
        artifact_path=tmp_path / "model.bin",
        horizon=2,
        predict_args={},
        rtol=1e-8,
        atol=1e-8,
    )
    assert result["status"] == "RUNTIME_CERTIFIED"

    predictions = [[1.0], [2.0]]
    seal = seal_predictions(
        "run-1",
        predictions,
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
    )
    assert verify_prediction_seal(seal, predictions)
    assert not verify_prediction_seal(seal, [[1.0], [3.0]])

    write_json(tmp_path / "result.json", result)
    manifest = finalize_manifest(tmp_path)
    assert manifest["file_count"] == 2
    persisted = json.loads((tmp_path / "ARTIFACT_MANIFEST.json").read_text(encoding="utf-8"))
    assert persisted == manifest
    for line in (tmp_path / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        assert hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest() == digest
