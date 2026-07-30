from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    production_os: Literal["linux"] = "linux"
    windows_role: Literal["auxiliary", "disaster_recovery"] = "auxiliary"
    wsl_role: Literal["compatibility", "disabled"] = "compatibility"
    production_slo_minutes: int = Field(default=180, ge=1)


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    holdout_draws: int = Field(default=50, ge=1)
    shadow_min_draws: int = Field(default=20, ge=1)
    shadow_formal_draws: int = Field(default=50, ge=1)
    provisional_hits_improvement: float = 0.10
    formal_hits_improvement: float = 0.15
    calibration_relative_margin: float = 0.02
    ece_absolute_margin: float = 0.02


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_backend: Literal["optuna"] = "optuna"
    ray_cpu_parallel_threshold: int = Field(default=4, ge=2)
    max_gpu_trial_concurrency: int = Field(default=1, ge=1)


class PlatformConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime: RuntimeConfig = RuntimeConfig()
    evaluation: EvaluationConfig = EvaluationConfig()
    search: SearchConfig = SearchConfig()
    feature_windows: tuple[int, ...] = (10, 30, 100)


def resolve_config(data: dict | None = None) -> dict:
    config = PlatformConfig.model_validate(data or {})
    resolved = config.model_dump(mode="json")
    payload = json.dumps(resolved, sort_keys=True, separators=(",", ":")).encode()
    return {"config": resolved, "sha256": hashlib.sha256(payload).hexdigest()}
