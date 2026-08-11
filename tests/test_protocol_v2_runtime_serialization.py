from __future__ import annotations

import json

import pytest

from loto.evaluation.protocol_v2 import canonical_json_bytes


class _FakeNeuralForecastLoss:
    __module__ = "neuralforecast.losses.pytorch"

    def __repr__(self) -> str:
        return "MAE()"


class _UnsupportedObject:
    pass


def test_canonical_json_serializes_neuralforecast_loss_runtime_evidence() -> None:
    payload = {"params": {"loss": _FakeNeuralForecastLoss()}}

    encoded = canonical_json_bytes(payload)
    decoded = json.loads(encoded)

    assert decoded["params"]["loss"] == {
        "__python_type__": (
            "neuralforecast.losses.pytorch._FakeNeuralForecastLoss"
        ),
        "__repr__": "MAE()",
    }


def test_canonical_json_still_rejects_unknown_python_objects() -> None:
    with pytest.raises(TypeError, match="not JSON serializable"):
        canonical_json_bytes({"unsupported": _UnsupportedObject()})
