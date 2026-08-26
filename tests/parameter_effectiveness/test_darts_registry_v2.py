from __future__ import annotations

import inspect

from loto.parameter_effectiveness import EffectSurface, ParameterProbeSpec, ParameterScope
from loto.parameter_effectiveness.extended_registry_v2 import DartsParameterAdapterV2


class _ModelMeta(type):
    def __call__(cls, *args, **kwargs):
        return super().__call__(*args, **kwargs)


class _FakeNaiveSeasonal(metaclass=_ModelMeta):
    def __init__(self, K: int = 1):
        self.K = K


def test_darts_v2_checks_init_signature_instead_of_metaclass_call(monkeypatch) -> None:
    adapter = DartsParameterAdapterV2()
    monkeypatch.setattr(adapter, "_imports", lambda: (object, _FakeNaiveSeasonal))

    class_signature = inspect.signature(_FakeNaiveSeasonal)
    init_signature = inspect.signature(_FakeNaiveSeasonal.__init__)

    assert "K" not in class_signature.parameters
    assert "K" in init_signature.parameters

    spec = ParameterProbeSpec(
        probe_id="darts-naive-seasonal-k-prediction",
        library="darts",
        model="NaiveSeasonal",
        parameter="K",
        scope=ParameterScope.MODEL_CONSTRUCTOR,
        control=1,
        treatment=7,
        expected_surface=EffectSurface.PREDICTION,
        seeds=(1, 42),
    )

    supported, reason = adapter.supports(spec)

    assert supported is True
    assert reason is None
