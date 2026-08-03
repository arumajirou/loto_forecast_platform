from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class NativePosterior:
    """Backend-neutral posterior contract.

    ``probability_draws`` is always shaped ``(draw, position, class)``.  Native
    backends may retain additional samples in ``native_payload`` but the lifecycle
    consumes only this normalized posterior-predictive probability tensor.
    """

    model_id: str
    backend: str
    family: str
    target_mode: str
    game: str
    probability_draws: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    native_payload: Any | None = None

    def __post_init__(self) -> None:
        draws = np.asarray(self.probability_draws, dtype=float)
        if draws.ndim == 2:
            draws = draws[:, None, :]
        if draws.ndim != 3:
            raise ValueError(
                f"probability_draws must have shape (draw, position, class); got {draws.shape}"
            )
        if draws.shape[0] < 1 or draws.shape[1] < 1 or draws.shape[2] < 2:
            raise ValueError(f"invalid probability_draws shape: {draws.shape}")
        if not np.isfinite(draws).all():
            raise ValueError("probability_draws contains non-finite values")
        draws = np.clip(draws, 1e-15, None)
        draws /= draws.sum(axis=-1, keepdims=True)
        self.probability_draws = draws

    @property
    def probabilities(self) -> np.ndarray:
        return self.probability_draws.mean(axis=0)

    @property
    def draw_count(self) -> int:
        return int(self.probability_draws.shape[0])

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "backend": self.backend,
            "family": self.family,
            "target_mode": self.target_mode,
            "game": self.game,
            "draw_shape": list(self.probability_draws.shape),
            "metadata": self.metadata,
            "diagnostics": self.diagnostics,
        }

    def save(self, directory: str | Path, *, save_draws: bool = True) -> list[Path]:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        if save_draws:
            draws_path = root / "posterior_probability_draws.npz"
            np.savez_compressed(draws_path, probability_draws=self.probability_draws)
            paths.append(draws_path)
        return paths


@dataclass(frozen=True)
class NativeImplementation:
    model_id: str
    primary_backend: str
    primary_profile: str | None
    implementation_kind: str
    module: str
    graph_id: str
    runtime_tier: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "primary_backend": self.primary_backend,
            "primary_profile": self.primary_profile,
            "implementation_kind": self.implementation_kind,
            "module": self.module,
            "graph_id": self.graph_id,
            "runtime_tier": self.runtime_tier,
        }
