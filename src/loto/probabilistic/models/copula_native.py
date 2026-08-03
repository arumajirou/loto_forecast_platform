from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
MODEL_ID = "pp-gaussian-copula-categorical"


def _validate_observations(y: np.ndarray, classes: int) -> FloatArray:
    values = np.asarray(y, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, None]
    if values.ndim != 2 or values.shape[0] < 2 or values.shape[1] < 2:
        raise ValueError("Gaussian copula observations must have shape (time, position>=2)")
    finite = values[np.isfinite(values)]
    if finite.size and (np.any(finite < 0) or np.any(finite >= classes)):
        raise ValueError("Gaussian copula observations contain an out-of-range category")
    if finite.size and not np.allclose(finite, np.round(finite)):
        raise ValueError("Gaussian copula observations must be integer categories or NaN")
    return values


def _nearest_correlation(matrix: FloatArray, floor: float) -> tuple[FloatArray, float]:
    symmetric = 0.5 * (matrix + matrix.T)
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    minimum = float(eigenvalues.min())
    clipped = np.maximum(eigenvalues, floor)
    repaired = (eigenvectors * clipped) @ eigenvectors.T
    scale = np.sqrt(np.clip(np.diag(repaired), floor, None))
    repaired = repaired / np.outer(scale, scale)
    repaired = 0.5 * (repaired + repaired.T)
    np.fill_diagonal(repaired, 1.0)
    if not np.isfinite(repaired).all():
        raise ValueError("COPULA_CORRELATION_INVALID: non-finite repaired correlation")
    return repaired.astype(np.float64), max(0.0, floor - minimum)


def estimate_marginal_probabilities(
    y: np.ndarray,
    *,
    classes: int,
    prior: float,
) -> FloatArray:
    values = _validate_observations(y, classes)
    probabilities = np.empty((values.shape[1], classes), dtype=np.float64)
    for position in range(values.shape[1]):
        observed = values[:, position]
        observed = observed[np.isfinite(observed)].astype(np.int64)
        counts = np.bincount(observed, minlength=classes).astype(np.float64)
        probabilities[position] = (counts + prior) / (counts.sum() + prior * classes)
    return probabilities


def thresholds_from_marginals(
    probabilities: np.ndarray,
    *,
    epsilon: float,
) -> FloatArray:
    values = np.asarray(probabilities, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] < 2:
        raise ValueError("marginal probabilities must have shape (position, class>=2)")
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("marginal probabilities must be finite and strictly positive")
    values = values / values.sum(axis=1, keepdims=True)
    thresholds = np.empty(
        (values.shape[0], values.shape[1] + 1), dtype=np.float64
    )
    thresholds[:, 0] = -np.inf
    thresholds[:, -1] = np.inf
    cumulative = np.cumsum(values, axis=1)[:, :-1]
    thresholds[:, 1:-1] = norm.ppf(np.clip(cumulative, epsilon, 1.0 - epsilon))
    if np.any(np.diff(thresholds, axis=1) <= 0):
        raise ValueError("COPULA_THRESHOLD_INVALID: thresholds are not strictly ordered")
    return thresholds


def latent_midpoint_scores(
    y: np.ndarray,
    probabilities: np.ndarray,
    *,
    epsilon: float,
) -> FloatArray:
    values = _validate_observations(y, probabilities.shape[1])
    probabilities = np.asarray(probabilities, dtype=np.float64)
    cumulative = np.cumsum(probabilities, axis=1)
    lower = np.concatenate(
        [np.zeros((probabilities.shape[0], 1), dtype=np.float64), cumulative[:, :-1]], axis=1
    )
    scores = np.full(values.shape, np.nan, dtype=np.float64)
    for position in range(values.shape[1]):
        observed_mask = np.isfinite(values[:, position])
        categories = values[observed_mask, position].astype(np.int64)
        midpoint = lower[position, categories] + 0.5 * probabilities[position, categories]
        scores[observed_mask, position] = norm.ppf(np.clip(midpoint, epsilon, 1.0 - epsilon))
    return scores


def estimate_latent_correlation(
    scores: np.ndarray,
    *,
    shrinkage: float,
    floor: float,
) -> tuple[FloatArray, float]:
    values = np.asarray(scores, dtype=np.float64)
    positions = values.shape[1]
    raw = np.eye(positions, dtype=np.float64)
    for left in range(positions):
        for right in range(left + 1, positions):
            mask = np.isfinite(values[:, left]) & np.isfinite(values[:, right])
            if int(mask.sum()) < 3:
                correlation = 0.0
            else:
                pair = values[mask][:, [left, right]]
                if np.min(np.std(pair, axis=0)) <= 1e-12:
                    correlation = 0.0
                else:
                    correlation = float(np.corrcoef(pair, rowvar=False)[0, 1])
            raw[left, right] = raw[right, left] = correlation
    shrunk = (1.0 - shrinkage) * raw + shrinkage * np.eye(positions, dtype=np.float64)
    return _nearest_correlation(shrunk, floor)


def categories_from_latent(latent: np.ndarray, thresholds: np.ndarray) -> IntArray:
    values = np.asarray(latent, dtype=np.float64)
    limits = np.asarray(thresholds, dtype=np.float64)
    if values.ndim == 1:
        values = values[None, :]
    if values.ndim != 2 or values.shape[1] != limits.shape[0]:
        raise ValueError("latent values and thresholds have incompatible position dimensions")
    output = np.empty(values.shape, dtype=np.int64)
    for position in range(values.shape[1]):
        output[:, position] = np.searchsorted(
            limits[position, 1:-1], values[:, position], side="right"
        )
    return output


@dataclass
class GaussianCopulaCategoricalState:
    model_id: str
    game: str
    classes: int
    positions: int
    marginal_probabilities: FloatArray
    thresholds: FloatArray
    correlation: FloatArray
    latent_scores: FloatArray
    label_order: tuple[tuple[int, ...], ...]
    marginal_prior: float
    correlation_shrinkage: float
    threshold_epsilon: float
    correlation_floor: float
    correlation_repair: float
    seed: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.marginal_probabilities = np.asarray(self.marginal_probabilities, dtype=np.float64)
        self.thresholds = np.asarray(self.thresholds, dtype=np.float64)
        self.correlation = np.asarray(self.correlation, dtype=np.float64)
        self.latent_scores = np.asarray(self.latent_scores, dtype=np.float64)
        if self.model_id != MODEL_ID:
            raise ValueError(f"unexpected copula model_id: {self.model_id}")
        if self.marginal_probabilities.shape != (self.positions, self.classes):
            raise ValueError("copula marginal probability shape mismatch")
        if self.thresholds.shape != (self.positions, self.classes + 1):
            raise ValueError("copula threshold shape mismatch")
        if self.correlation.shape != (self.positions, self.positions):
            raise ValueError("copula correlation shape mismatch")
        if self.latent_scores.ndim != 2 or self.latent_scores.shape[1] != self.positions:
            raise ValueError("copula latent score shape mismatch")
        if len(self.label_order) != self.positions:
            raise ValueError("copula label order position count mismatch")
        expected_labels = tuple(range(self.classes))
        if any(tuple(labels) != expected_labels for labels in self.label_order):
            raise ValueError("copula label order must preserve zero-based categorical order")
        if not np.isfinite(self.marginal_probabilities).all():
            raise ValueError("copula marginals contain non-finite values")
        if np.any(self.marginal_probabilities <= 0):
            raise ValueError("copula marginals must be strictly positive")
        if not np.allclose(self.marginal_probabilities.sum(axis=1), 1.0, atol=1e-10):
            raise ValueError("copula marginals are not simplex-valid")
        if not np.allclose(self.correlation, self.correlation.T, atol=1e-10):
            raise ValueError("copula correlation is not symmetric")
        if not np.allclose(np.diag(self.correlation), 1.0, atol=1e-10):
            raise ValueError("copula correlation diagonal is not one")
        if float(np.linalg.eigvalsh(self.correlation).min()) < -1e-9:
            raise ValueError("COPULA_CORRELATION_INVALID: correlation is not PSD")
        if np.any(np.diff(self.thresholds, axis=1) <= 0):
            raise ValueError("COPULA_THRESHOLD_INVALID: thresholds are not ordered")

    def probability_draws(self, draws: int) -> FloatArray:
        if draws < 1:
            raise ValueError("draws must be positive")
        return np.repeat(self.marginal_probabilities[None, :, :], draws, axis=0)

    def joint_samples(
        self,
        *,
        draws: int,
        seed: int,
        correlation: np.ndarray | None = None,
    ) -> IntArray:
        if draws < 1:
            raise ValueError("draws must be positive")
        selected = self.correlation if correlation is None else np.asarray(correlation, dtype=float)
        selected, _ = _nearest_correlation(selected, self.correlation_floor)
        rng = np.random.default_rng(seed)
        latent = rng.multivariate_normal(
            mean=np.zeros(self.positions, dtype=np.float64),
            cov=selected,
            size=draws,
            check_valid="raise",
        )
        return categories_from_latent(latent, self.thresholds)

    def empirical_marginals(self, samples: np.ndarray) -> FloatArray:
        values = np.asarray(samples, dtype=np.int64)
        if values.ndim != 2 or values.shape[1] != self.positions:
            raise ValueError("joint samples have invalid shape")
        output = np.empty((self.positions, self.classes), dtype=np.float64)
        for position in range(self.positions):
            output[position] = np.bincount(
                values[:, position], minlength=self.classes
            ) / len(values)
        return output

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "game": self.game,
            "classes": self.classes,
            "positions": self.positions,
            "marginal_probabilities": self.marginal_probabilities.tolist(),
            "thresholds": self.thresholds.tolist(),
            "correlation": self.correlation.tolist(),
            "label_order": [list(labels) for labels in self.label_order],
            "marginal_prior": self.marginal_prior,
            "correlation_shrinkage": self.correlation_shrinkage,
            "threshold_epsilon": self.threshold_epsilon,
            "correlation_floor": self.correlation_floor,
            "correlation_repair": self.correlation_repair,
            "seed": self.seed,
            "metadata": self.metadata,
        }

    def save(self, directory: str | Path) -> list[Path]:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        metadata_path = root / "copula_state.json"
        arrays_path = root / "copula_state.npz"
        metadata_path.write_text(
            json.dumps(self.to_metadata_dict(), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        np.savez_compressed(
            arrays_path,
            marginal_probabilities=self.marginal_probabilities,
            thresholds=self.thresholds,
            correlation=self.correlation,
            latent_scores=self.latent_scores,
        )
        return [metadata_path, arrays_path]

    @classmethod
    def load(cls, directory: str | Path) -> GaussianCopulaCategoricalState:
        root = Path(directory)
        metadata = json.loads((root / "copula_state.json").read_text(encoding="utf-8"))
        with np.load(root / "copula_state.npz") as arrays:
            return cls(
                model_id=str(metadata["model_id"]),
                game=str(metadata["game"]),
                classes=int(metadata["classes"]),
                positions=int(metadata["positions"]),
                marginal_probabilities=arrays["marginal_probabilities"],
                thresholds=arrays["thresholds"],
                correlation=arrays["correlation"],
                latent_scores=arrays["latent_scores"],
                label_order=tuple(
                    tuple(int(item) for item in row) for row in metadata["label_order"]
                ),
                marginal_prior=float(metadata["marginal_prior"]),
                correlation_shrinkage=float(metadata["correlation_shrinkage"]),
                threshold_epsilon=float(metadata["threshold_epsilon"]),
                correlation_floor=float(metadata["correlation_floor"]),
                correlation_repair=float(metadata["correlation_repair"]),
                seed=int(metadata["seed"]),
                metadata=dict(metadata.get("metadata", {})),
            )


def fit_gaussian_copula_categorical(
    y: np.ndarray,
    *,
    game: str,
    classes: int,
    config: Any,
    seed: int,
) -> GaussianCopulaCategoricalState:
    values = _validate_observations(y, classes)
    probabilities = estimate_marginal_probabilities(
        values,
        classes=classes,
        prior=float(config.copula_marginal_prior),
    )
    thresholds = thresholds_from_marginals(
        probabilities,
        epsilon=float(config.copula_threshold_epsilon),
    )
    scores = latent_midpoint_scores(
        values,
        probabilities,
        epsilon=float(config.copula_threshold_epsilon),
    )
    correlation, repair = estimate_latent_correlation(
        scores,
        shrinkage=float(config.copula_correlation_shrinkage),
        floor=float(config.copula_correlation_floor),
    )
    positions = values.shape[1]
    return GaussianCopulaCategoricalState(
        model_id=MODEL_ID,
        game=game,
        classes=classes,
        positions=positions,
        marginal_probabilities=probabilities,
        thresholds=thresholds,
        correlation=correlation,
        latent_scores=scores,
        label_order=tuple(tuple(range(classes)) for _ in range(positions)),
        marginal_prior=float(config.copula_marginal_prior),
        correlation_shrinkage=float(config.copula_correlation_shrinkage),
        threshold_epsilon=float(config.copula_threshold_epsilon),
        correlation_floor=float(config.copula_correlation_floor),
        correlation_repair=repair,
        seed=seed,
        metadata={
            "marginal_estimator": "dirichlet_smoothed_empirical",
            "latent_transform": "distributional_midpoint",
            "dependence_estimator": "pairwise_latent_correlation_with_psd_repair",
            "threshold_fit_scope": "training_rows_only",
        },
    )


__all__ = [
    "MODEL_ID",
    "GaussianCopulaCategoricalState",
    "categories_from_latent",
    "estimate_latent_correlation",
    "estimate_marginal_probabilities",
    "fit_gaussian_copula_categorical",
    "latent_midpoint_scores",
    "thresholds_from_marginals",
]
