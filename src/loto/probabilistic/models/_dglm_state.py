from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from loto.probabilistic.models._dglm_math import (
    MODEL_ID,
    FloatArray,
    _block_diagonal,
    _ensure_psd,
    _feature_vector,
    _softmax_reference,
    _state_structure,
)


@dataclass
class MultinomialDGLMState:
    model_id: str
    game: str
    classes: int
    positions: int
    state_names: tuple[str, ...]
    include_trend: bool
    seasonal_periods: tuple[float, ...]
    exogenous_dim: int
    discount_factor: float
    observation_jitter: float
    covariance_floor: float
    current_step: int
    state_mean: FloatArray
    state_covariance: FloatArray
    one_step_probabilities: FloatArray
    update_applied: NDArray[np.bool_]
    max_covariance_jitter: float
    max_innovation_condition: float
    seed: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.state_mean = np.asarray(self.state_mean, dtype=np.float64)
        self.state_covariance = np.asarray(self.state_covariance, dtype=np.float64)
        self.one_step_probabilities = np.asarray(
            self.one_step_probabilities, dtype=np.float64
        )
        self.update_applied = np.asarray(self.update_applied, dtype=bool)
        if self.model_id != MODEL_ID:
            raise ValueError(f"unexpected model_id: {self.model_id}")
        state_dim = len(self.state_names)
        flat_dim = (self.classes - 1) * state_dim
        if self.state_mean.shape != (self.positions, flat_dim):
            raise ValueError("state_mean shape does not match positions/classes/state dimension")
        if self.state_covariance.shape != (self.positions, flat_dim, flat_dim):
            raise ValueError("state_covariance shape does not match state_mean")
        if self.one_step_probabilities.ndim != 3:
            raise ValueError("one_step_probabilities must have shape (time, position, class)")
        if self.one_step_probabilities.shape[1:] != (self.positions, self.classes):
            raise ValueError("one_step_probabilities position/class shape mismatch")
        if self.update_applied.shape != self.one_step_probabilities.shape[:2]:
            raise ValueError("update_applied must have shape (time, position)")
        arrays = (self.state_mean, self.state_covariance, self.one_step_probabilities)
        if not all(np.isfinite(array).all() for array in arrays):
            raise ValueError("DGLM_FILTER_DIVERGED: state contains non-finite values")
        if not np.allclose(self.one_step_probabilities.sum(axis=-1), 1.0, atol=1e-8):
            raise ValueError("DGLM predictive probabilities do not sum to one")
        for covariance in self.state_covariance:
            if not np.allclose(covariance, covariance.T, atol=1e-9):
                raise ValueError("DGLM covariance is not symmetric")
            if float(np.linalg.eigvalsh(covariance).min()) < -1e-8:
                raise ValueError("DGLM covariance is not PSD")

    @property
    def state_dim(self) -> int:
        return len(self.state_names)

    @property
    def flat_state_dim(self) -> int:
        return (self.classes - 1) * self.state_dim

    def _evolution(self) -> FloatArray:
        _, state_evolution = _state_structure(
            include_trend=self.include_trend,
            seasonal_periods=self.seasonal_periods,
            exogenous_dim=self.exogenous_dim,
        )
        return _block_diagonal(state_evolution, self.classes - 1)

    def _feature(self, exogenous: np.ndarray | None = None) -> FloatArray:
        if self.exogenous_dim:
            if exogenous is None:
                raise ValueError("next exogenous vector is required for this DGLM state")
            values = np.asarray(exogenous, dtype=np.float64)
            if values.shape != (self.exogenous_dim,) or not np.isfinite(values).all():
                raise ValueError("next exogenous vector has the wrong shape or non-finite values")
        else:
            values = None
        return _feature_vector(
            step=self.current_step,
            include_trend=self.include_trend,
            seasonal_periods=self.seasonal_periods,
            exogenous=values,
        )

    def predictive_probabilities(self, exogenous: np.ndarray | None = None) -> FloatArray:
        feature = self._feature(exogenous)
        output = np.empty((self.positions, self.classes), dtype=np.float64)
        for position in range(self.positions):
            coefficients = self.state_mean[position].reshape(self.classes - 1, self.state_dim)
            output[position] = _softmax_reference(coefficients @ feature)
        return output

    def probability_draws(
        self,
        *,
        draws: int,
        seed: int,
        exogenous: np.ndarray | None = None,
    ) -> FloatArray:
        if draws < 1:
            raise ValueError("draws must be positive")
        feature = self._feature(exogenous)
        rng = np.random.default_rng(seed)
        output = np.empty((draws, self.positions, self.classes), dtype=np.float64)
        for position in range(self.positions):
            covariance, _ = _ensure_psd(
                self.state_covariance[position], self.covariance_floor
            )
            samples = rng.multivariate_normal(
                self.state_mean[position], covariance, size=draws, check_valid="raise"
            )
            coefficients = samples.reshape(draws, self.classes - 1, self.state_dim)
            logits = np.einsum("dcs,s->dc", coefficients, feature)
            for draw_index in range(draws):
                output[draw_index, position] = _softmax_reference(logits[draw_index])
        return output

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "model_id": self.model_id,
            "game": self.game,
            "classes": self.classes,
            "positions": self.positions,
            "state_names": list(self.state_names),
            "include_trend": self.include_trend,
            "seasonal_periods": list(self.seasonal_periods),
            "exogenous_dim": self.exogenous_dim,
            "discount_factor": self.discount_factor,
            "observation_jitter": self.observation_jitter,
            "covariance_floor": self.covariance_floor,
            "current_step": self.current_step,
            "history_rows": int(self.one_step_probabilities.shape[0]),
            "max_covariance_jitter": self.max_covariance_jitter,
            "max_innovation_condition": self.max_innovation_condition,
            "seed": self.seed,
            "metadata": self.metadata,
        }

    def save(self, directory: str | Path) -> list[Path]:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        metadata_path = root / "multinomial_dglm_state.json"
        arrays_path = root / "multinomial_dglm_state.npz"
        metadata_path.write_text(
            json.dumps(self.to_metadata_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        np.savez_compressed(
            arrays_path,
            state_mean=self.state_mean,
            state_covariance=self.state_covariance,
            one_step_probabilities=self.one_step_probabilities,
            update_applied=self.update_applied,
        )
        return [metadata_path, arrays_path]

    @classmethod
    def load(cls, directory: str | Path) -> MultinomialDGLMState:
        root = Path(directory)
        metadata = json.loads((root / "multinomial_dglm_state.json").read_text("utf-8"))
        arrays = np.load(root / "multinomial_dglm_state.npz")
        return cls(
            model_id=str(metadata["model_id"]),
            game=str(metadata["game"]),
            classes=int(metadata["classes"]),
            positions=int(metadata["positions"]),
            state_names=tuple(str(item) for item in metadata["state_names"]),
            include_trend=bool(metadata["include_trend"]),
            seasonal_periods=tuple(float(item) for item in metadata["seasonal_periods"]),
            exogenous_dim=int(metadata["exogenous_dim"]),
            discount_factor=float(metadata["discount_factor"]),
            observation_jitter=float(metadata["observation_jitter"]),
            covariance_floor=float(metadata["covariance_floor"]),
            current_step=int(metadata["current_step"]),
            state_mean=arrays["state_mean"],
            state_covariance=arrays["state_covariance"],
            one_step_probabilities=arrays["one_step_probabilities"],
            update_applied=arrays["update_applied"],
            max_covariance_jitter=float(metadata["max_covariance_jitter"]),
            max_innovation_condition=float(metadata["max_innovation_condition"]),
            seed=int(metadata["seed"]),
            metadata=dict(metadata.get("metadata") or {}),
        )
