from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TrialTiming:
    build_seconds: float = 0.0
    inference_seconds: float = 0.0
    predictive_seconds: float = 0.0
