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
