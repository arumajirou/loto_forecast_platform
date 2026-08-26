from __future__ import annotations

from loto.parameter_effectiveness.adapters import default_registry
from loto.parameter_effectiveness.extended_adapters import register_extended_adapters


def test_extended_registry_is_lazy_and_complete() -> None:
    registry = default_registry()
    register_extended_adapters(registry)

    libraries = registry.libraries()

    assert "mlforecast" in libraries
    assert "automlforecast" in libraries
    assert "statsforecast" in libraries
    assert "darts" in libraries
    assert "sktime" in libraries
    assert "gluonts" in libraries
    assert "toto2" in libraries
    assert "toto" in libraries
