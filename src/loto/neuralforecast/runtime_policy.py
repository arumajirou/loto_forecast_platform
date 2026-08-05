from __future__ import annotations

import random
from typing import Any, Literal

import numpy as np

PredictionComparisonPolicy = Literal["deterministic", "stochastic"]

_STOCHASTIC_MODEL_NAMES = {
    "DeepAR",
    "DeepNPTS",
    "TFT",
    "HINT",
    "AutoDeepAR",
    "AutoDeepNPTS",
    "AutoTFT",
    "AutoHINT",
}


def seed_runtime(seed: int) -> None:
    """Reset Python, NumPy and Torch RNGs before a reproducibility sample."""

    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
    except ImportError:
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_prediction_policy(
    neuralforecast: Any,
    requested: PredictionComparisonPolicy | None,
) -> PredictionComparisonPolicy:
    if requested is not None:
        return requested
    models = getattr(neuralforecast, "models", None) or []
    names: set[str] = set()
    for model in models:
        names.add(type(model).__name__)
        inner = getattr(model, "model", None)
        if inner is not None:
            names.add(type(inner).__name__)
    return "stochastic" if names & _STOCHASTIC_MODEL_NAMES else "deterministic"


def precision_tolerance(precision: str | None) -> tuple[float, float]:
    value = str(precision or "32-true").lower()
    if "64" in value:
        return 1e-8, 1e-8
    if "bf16" in value or "16" in value:
        return 5e-3, 5e-3
    return 1e-6, 1e-6
