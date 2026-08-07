"""Isolated StatsForecast campaign contracts.

This package deliberately avoids shared worker, catalog, dependency, and CLI paths.
"""

from .contracts import (
    ArgumentState,
    CampaignConfig,
    ExpectedStatus,
    GameGeometry,
    RuntimeStatus,
    TimeAxisContract,
    TimeAxisMode,
)
from .inventory import MODEL_CONTRACTS, MODEL_NAMES, model_contract

__all__ = [
    "ArgumentState",
    "certify_installed_runtime",
    "CampaignConfig",
    "ExpectedStatus",
    "GameGeometry",
    "MODEL_CONTRACTS",
    "MODEL_NAMES",
    "RuntimeStatus",
    "TimeAxisContract",
    "TimeAxisMode",
    "model_contract",
]


def certify_installed_runtime(*args, **kwargs):
    """Load the runtime certifier lazily to keep ``python -m`` warning-free."""

    from .certify import certify_installed_runtime as _certify

    return _certify(*args, **kwargs)
