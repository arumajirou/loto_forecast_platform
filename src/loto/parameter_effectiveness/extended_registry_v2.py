"""Phase 5B registry fixes for runtime-specific constructor introspection."""

from __future__ import annotations

import inspect

from .contracts import EffectSurface, ParameterProbeSpec, ParameterScope
from .extended_adapters import (
    DartsParameterAdapter,
    GluonTSParameterAdapter,
    SktimeParameterAdapter,
    Toto2ParameterAdapter,
)


class DartsParameterAdapterV2(DartsParameterAdapter):
    """Darts adapter that inspects ``__init__`` instead of the metaclass call signature."""

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        try:
            _, model_class = self._imports()
        except ImportError as exc:
            return False, f"Darts unavailable: {exc}"
        if spec.model != "NaiveSeasonal":
            return False, f"unsupported Darts model: {spec.model}"
        if spec.scope not in {ParameterScope.AUTO, ParameterScope.MODEL_CONSTRUCTOR}:
            return False, "Darts adapter probes NaiveSeasonal model-constructor arguments"

        constructor_signature = inspect.signature(model_class.__init__)
        if spec.parameter not in constructor_signature.parameters:
            return False, f"{spec.parameter!r} is not in NaiveSeasonal __init__ constructor"
        if spec.expected_surface in {EffectSurface.TRIAL_COUNT, EffectSurface.HISTORY}:
            return False, f"{spec.expected_surface.value} is not exposed by Darts adapter"
        return True, None


def register_extended_adapters_v2(registry) -> None:
    """Register Phase 5B adapters with corrected Darts constructor introspection."""

    registry.register(DartsParameterAdapterV2())
    registry.register(SktimeParameterAdapter())
    registry.register(GluonTSParameterAdapter())
    registry.register(Toto2ParameterAdapter(), "toto")
