"""Leakage-safe NeuralForecast all-AutoModel campaign."""

__version__ = "1.1.0"

from .contracts import CampaignConfig as CampaignConfig
from .contracts import CampaignStage as CampaignStage
from .registry import AutoModelRecord as AutoModelRecord
from .registry import discover_auto_models as discover_auto_models

__all__ = [
    "AutoModelRecord",
    "CampaignConfig",
    "CampaignStage",
    "discover_auto_models",
    "__version__",
]
