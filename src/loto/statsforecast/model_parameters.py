"""Shared public constructor-parameter contract for StatsForecast models.

The authoritative resolver implementation currently remains in
``loto.statsforecast.certification_models`` so the already-merged runtime/property
certification behavior does not change while Phase C adopts the same parameter contract.
Real-game runtime code should import from this module instead of depending on the
certification module directly.
"""

from __future__ import annotations

from .certification_models import required_parameters, resolve_parameters

__all__ = [
    "required_parameters",
    "resolve_parameters",
]
