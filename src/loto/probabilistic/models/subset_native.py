from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from loto.probabilistic.math.elementary_symmetric import (
    conditional_bernoulli_log_probability,
    fixed_cardinality_marginals,
    log_elementary_symmetric,
    sample_conditional_bernoulli,
)

MODEL_ID = "pp-conditional-bernoulli-fixed-k"
FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


def _logmeanexp(values: FloatArray) -> float:
    if values.ndim != 1 or values.size == 0:
        raise ValueError("values must be a non-empty one-dimensional array")
    maximum = float(np.max(values))
    if np.isneginf(maximum):
        return float("-inf")
    return maximum + float(np.log(np.mean(np.exp(values - maximum))))


def _validate_indicator_matrix(
    y: np.ndarray, cardinality: int | None = None
) -> tuple[IntArray, int]:
    values = np.asarray(y, dtype=np.int64)
    if values.ndim != 2 or values.shape[0] < 1 or values.shape[1] < 2:
        raise ValueError("fixed-k training data must have shape (row, candidate)")
    if not np.isin(values, (0, 1)).all():
        raise ValueError("fixed-k training data must contain only 0/1 indicators")
    row_sums = values.sum(axis=1)
    inferred = int(row_sums[0])
    if inferred < 1 or inferred >= values.shape[1]:
        raise ValueError("fixed-k cardinality must be in [1, candidates - 1]")
    if not np.all(row_sums == inferred):
        raise ValueError("fixed-k training rows must all have the same cardinality")
    if cardinality is not None and inferred != cardinality:
        raise ValueError(f"expected cardinality {cardinality}, got {inferred}")
    return values, inferred


def fixed_cardinality_covariance(log_weights: np.ndarray, cardinality: int) -> FloatArray:
    """Return the exact covariance of inclusion indicators under a fixed-k law."""

    logits = np.asarray(log_weights, dtype=np.float64)
    if logits.ndim != 1:
        raise ValueError("log_weights must be one-dimensional")
    marginals = fixed_cardinality_marginals(logits, cardinality)
    covariance = np.diag(marginals * (1.0 - marginals)).astype(np.float64)
    if cardinality < 2:
        covariance -= np.outer(marginals, marginals)
        np.fill_diagonal(covariance, marginals * (1.0 - marginals))
        return covariance

    log_normalizer = log_elementary_symmetric(logits, cardinality)
    for left in range(logits.size):
        for right in range(left + 1, logits.size):
            reduced = np.delete(logits, (left, right))
            log_excluding = log_elementary_symmetric(reduced, cardinality - 2)
            pair_probability = float(
                np.exp(logits[left] + logits[right] + log_excluding - log_normalizer)
            )
            value = pair_probability - marginals[left] * marginals[right]
            covariance[left, right] = value
            covariance[right, left] = value
    return covariance


def _objective_and_gradient(
    logits: FloatArray,
    *,
    counts: FloatArray,
    rows: int,
    cardinality: int,
    prior_scale: float,
) -> tuple[float, FloatArray]:
    centered = logits - float(np.mean(logits))
    log_normalizer = log_elementary_symmetric(centered, cardinality)
    marginals = fixed_cardinality_marginals(centered, cardinality)
    precision = 1.0 / (prior_scale * prior_scale)
    objective = (
        rows * log_normalizer
        - float(np.dot(counts, centered))
        + 0.5 * precision * float(np.dot(centered, centered))
    )
    gradient = rows * marginals - counts + precision * centered
    gradient -= float(np.mean(gradient))
    return float(objective), gradient.astype(np.float64)


def _laplace_covariance(
    map_logits: FloatArray,
    *,
    rows: int,
    cardinality: int,
    prior_scale: float,
    initial_ridge: float,
) -> tuple[FloatArray, float]:
    precision = 1.0 / (prior_scale * prior_scale)
    hessian = rows * fixed_cardinality_covariance(map_logits, cardinality)
    hessian += np.eye(map_logits.size, dtype=np.float64) * precision
    hessian = 0.5 * (hessian + hessian.T)

    ridge = max(float(initial_ridge), 0.0)
    identity = np.eye(map_logits.size, dtype=np.float64)
    for _ in range(12):
        candidate = hessian + ridge * identity
        try:
            np.linalg.cholesky(candidate)
            covariance = np.linalg.inv(candidate)
            covariance = 0.5 * (covariance + covariance.T)
            return covariance.astype(np.float64), ridge
        except np.linalg.LinAlgError:
            ridge = 1e-10 if ridge == 0.0 else ridge * 10.0
    raise ValueError("Laplace Hessian remained non-positive-definite after ridge escalation")


@dataclass
class ConditionalBernoulliPosterior:
    model_id: str
    game: str
    cardinality: int
    map_logits: FloatArray
    covariance: FloatArray
    logit_draws: FloatArray
    candidate_marginal_draws: FloatArray
    joint_samples: IntArray
    training_rows: int
    optimizer_success: bool
    optimizer_message: str
    optimizer_iterations: int
    objective_value: float
    gradient_norm: float
    laplace_ridge: float
    seed: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.map_logits = np.asarray(self.map_logits, dtype=np.float64)
        self.covariance = np.asarray(self.covariance, dtype=np.float64)
        self.logit_draws = np.asarray(self.logit_draws, dtype=np.float64)
        self.candidate_marginal_draws = np.asarray(self.candidate_marginal_draws, dtype=np.float64)
        self.joint_samples = np.asarray(self.joint_samples, dtype=np.int64)
        candidates = self.map_logits.size
        if self.model_id != MODEL_ID:
            raise ValueError(f"unexpected model_id: {self.model_id}")
        if self.covariance.shape != (candidates, candidates):
            raise ValueError("covariance shape does not match map_logits")
        if self.logit_draws.ndim != 2 or self.logit_draws.shape[1] != candidates:
            raise ValueError("logit_draws must have shape (draw, candidate)")
        if self.candidate_marginal_draws.shape != self.logit_draws.shape:
            raise ValueError("candidate_marginal_draws must match logit_draws")
        if self.joint_samples.shape != (self.logit_draws.shape[0], self.cardinality):
            raise ValueError("joint_samples must have shape (draw, cardinality)")
        arrays = (
            self.map_logits,
            self.covariance,
            self.logit_draws,
            self.candidate_marginal_draws,
        )
        if not all(np.isfinite(array).all() for array in arrays):
            raise ValueError("posterior contains non-finite values")
        if not np.allclose(self.candidate_marginal_draws.sum(axis=1), self.cardinality, atol=1e-8):
            raise ValueError("candidate marginals do not sum to cardinality")
        for sample in self.joint_samples:
            if len(set(sample.tolist())) != self.cardinality:
                raise ValueError("joint sample contains duplicates")
            if np.any(sample < 0) or np.any(sample >= candidates):
                raise ValueError("joint sample contains an out-of-range candidate")

    @property
    def candidates(self) -> int:
        return int(self.map_logits.size)

    @property
    def draw_count(self) -> int:
        return int(self.logit_draws.shape[0])

    @property
    def candidate_marginals(self) -> FloatArray:
        return self.candidate_marginal_draws.mean(axis=0)

    @property
    def normalized_probability_draws(self) -> FloatArray:
        return (self.candidate_marginal_draws / self.cardinality)[:, None, :]

    @property
    def point_indices(self) -> tuple[int, ...]:
        chosen = np.argpartition(self.candidate_marginals, -self.cardinality)[-self.cardinality :]
        return tuple(sorted(int(index) for index in chosen))

    def posterior_predictive_log_probability(self, subset: list[int] | tuple[int, ...]) -> float:
        chosen = tuple(int(index) for index in subset)
        log_probabilities = np.asarray(
            [
                conditional_bernoulli_log_probability(draw, chosen, self.cardinality)
                for draw in self.logit_draws
            ],
            dtype=np.float64,
        )
        return _logmeanexp(log_probabilities)

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "model_id": self.model_id,
            "game": self.game,
            "cardinality": self.cardinality,
            "candidates": self.candidates,
            "draw_count": self.draw_count,
            "training_rows": self.training_rows,
            "optimizer_success": self.optimizer_success,
            "optimizer_message": self.optimizer_message,
            "optimizer_iterations": self.optimizer_iterations,
            "objective_value": self.objective_value,
            "gradient_norm": self.gradient_norm,
            "laplace_ridge": self.laplace_ridge,
            "seed": self.seed,
            "point_indices": list(self.point_indices),
            "candidate_marginal_sum": float(self.candidate_marginals.sum()),
            "metadata": self.metadata,
        }

    def save(self, directory: str | Path) -> list[Path]:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        metadata_path = root / "conditional_bernoulli_posterior.json"
        arrays_path = root / "conditional_bernoulli_posterior.npz"
        metadata_path.write_text(
            json.dumps(self.to_metadata_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        np.savez_compressed(
            arrays_path,
            map_logits=self.map_logits,
            covariance=self.covariance,
            logit_draws=self.logit_draws,
            candidate_marginal_draws=self.candidate_marginal_draws,
            joint_samples=self.joint_samples,
        )
        return [metadata_path, arrays_path]

    @classmethod
    def load(cls, directory: str | Path) -> ConditionalBernoulliPosterior:
        root = Path(directory)
        metadata = json.loads(
            (root / "conditional_bernoulli_posterior.json").read_text(encoding="utf-8")
        )
        arrays = np.load(root / "conditional_bernoulli_posterior.npz")
        return cls(
            model_id=str(metadata["model_id"]),
            game=str(metadata["game"]),
            cardinality=int(metadata["cardinality"]),
            map_logits=arrays["map_logits"],
            covariance=arrays["covariance"],
            logit_draws=arrays["logit_draws"],
            candidate_marginal_draws=arrays["candidate_marginal_draws"],
            joint_samples=arrays["joint_samples"],
            training_rows=int(metadata["training_rows"]),
            optimizer_success=bool(metadata["optimizer_success"]),
            optimizer_message=str(metadata["optimizer_message"]),
            optimizer_iterations=int(metadata["optimizer_iterations"]),
            objective_value=float(metadata["objective_value"]),
            gradient_norm=float(metadata["gradient_norm"]),
            laplace_ridge=float(metadata["laplace_ridge"]),
            seed=int(metadata["seed"]),
            metadata=dict(metadata.get("metadata") or {}),
        )


def fit_conditional_bernoulli_map(
    y: np.ndarray,
    *,
    game: str,
    config: Any,
    seed: int,
    cardinality: int | None = None,
) -> ConditionalBernoulliPosterior:
    """Closure-based public entry point used by backend execution.

    This wrapper exists because SciPy accepts positional ``args`` but the core
    objective intentionally uses keyword-only arguments for auditability.
    """

    values, inferred_cardinality = _validate_indicator_matrix(y, cardinality)
    max_rows = int(config.native_max_train_rows)
    values = values[-min(len(values), max_rows) :]
    rows, candidates = values.shape
    counts = values.sum(axis=0).astype(np.float64)
    prior_scale = float(config.subset_prior_scale)
    initial = np.log(counts + float(config.subset_initial_pseudocount))
    initial -= float(np.mean(initial))

    def objective(logits: FloatArray) -> tuple[float, FloatArray]:
        return _objective_and_gradient(
            logits,
            counts=counts,
            rows=rows,
            cardinality=inferred_cardinality,
            prior_scale=prior_scale,
        )

    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        options={
            "maxiter": int(config.subset_max_iter),
            "ftol": float(config.subset_tolerance),
            "gtol": float(config.subset_tolerance),
            "maxls": 50,
        },
    )
    map_logits = np.asarray(result.x, dtype=np.float64)
    map_logits -= float(np.mean(map_logits))
    objective_value, gradient = objective(map_logits)
    gradient_norm = float(np.linalg.norm(gradient, ord=np.inf))
    if bool(config.subset_require_convergence) and (
        not bool(result.success) or gradient_norm > float(config.subset_gradient_tolerance)
    ):
        raise ValueError(
            "conditional Bernoulli optimizer did not converge: "
            f"success={result.success}, gradient_norm={gradient_norm:.6g}, "
            f"message={result.message}"
        )
    covariance, applied_ridge = _laplace_covariance(
        map_logits,
        rows=rows,
        cardinality=inferred_cardinality,
        prior_scale=prior_scale,
        initial_ridge=float(config.subset_laplace_ridge),
    )
    draw_count = int(
        config.native_draws
        if str(config.backend_policy) == "primary_native"
        else config.posterior_draws
    )
    rng = np.random.default_rng(seed)
    logit_draws = rng.multivariate_normal(
        mean=map_logits,
        cov=covariance,
        size=draw_count,
        check_valid="raise",
    ).astype(np.float64)
    logit_draws -= logit_draws.mean(axis=1, keepdims=True)
    marginal_draws = np.vstack(
        [fixed_cardinality_marginals(draw, inferred_cardinality) for draw in logit_draws]
    ).astype(np.float64)
    joint_samples = np.asarray(
        [sample_conditional_bernoulli(draw, inferred_cardinality, rng=rng) for draw in logit_draws],
        dtype=np.int64,
    )
    return ConditionalBernoulliPosterior(
        model_id=MODEL_ID,
        game=game,
        cardinality=inferred_cardinality,
        map_logits=map_logits,
        covariance=covariance,
        logit_draws=logit_draws,
        candidate_marginal_draws=marginal_draws,
        joint_samples=joint_samples,
        training_rows=rows,
        optimizer_success=bool(result.success),
        optimizer_message=str(result.message),
        optimizer_iterations=int(getattr(result, "nit", 0)),
        objective_value=float(objective_value),
        gradient_norm=gradient_norm,
        laplace_ridge=applied_ridge,
        seed=seed,
        metadata={
            "algorithm": "MAP_LAPLACE",
            "optimizer": "L-BFGS-B",
            "normalizer": "exact_log_space_elementary_symmetric_dp",
            "sampler": "exact_backward_dynamic_programming",
            "prior_scale": prior_scale,
            "candidate_count": candidates,
            "fixed_cardinality": inferred_cardinality,
            "training_rows_requested": int(len(y)),
            "training_rows_used": rows,
        },
    )


def uniform_fixed_k_log_probability(candidates: int, cardinality: int) -> float:
    if candidates < 1 or cardinality < 0 or cardinality > candidates:
        raise ValueError("invalid candidates/cardinality")
    return -(
        math.lgamma(candidates + 1)
        - math.lgamma(cardinality + 1)
        - math.lgamma(candidates - cardinality + 1)
    )


def frequency_fixed_k_log_probability(
    training_indicator: np.ndarray,
    actual_subset: list[int] | tuple[int, ...],
    *,
    pseudocount: float = 1.0,
) -> float:
    values, cardinality = _validate_indicator_matrix(training_indicator)
    if pseudocount <= 0.0:
        raise ValueError("pseudocount must be positive")
    log_weights = np.log(values.sum(axis=0).astype(float) + pseudocount)
    return conditional_bernoulli_log_probability(log_weights, actual_subset, cardinality)


def symbolic_log_elementary_symmetric(
    pt: Any, logits: Any, cardinality: int, candidates: int
) -> Any:
    """PyTensor-compatible exact log-space elementary symmetric DP."""

    dp = [pt.as_tensor_variable(0.0)] + [pt.as_tensor_variable(-np.inf)] * cardinality
    for index in range(candidates):
        updated = list(dp)
        for degree in range(min(index + 1, cardinality), 0, -1):
            updated[degree] = pt.logaddexp(dp[degree], dp[degree - 1] + logits[index])
        dp = updated
    return dp[cardinality]


def symbolic_fixed_cardinality_marginals(
    pt: Any, logits: Any, cardinality: int, candidates: int
) -> Any:
    log_normalizer = symbolic_log_elementary_symmetric(pt, logits, cardinality, candidates)
    marginals = []
    for excluded in range(candidates):
        reduced = pt.concatenate([logits[:excluded], logits[excluded + 1 :]])
        log_excluding = symbolic_log_elementary_symmetric(
            pt, reduced, cardinality - 1, candidates - 1
        )
        marginals.append(pt.exp(logits[excluded] + log_excluding - log_normalizer))
    return pt.stack(marginals)


__all__ = [
    "MODEL_ID",
    "ConditionalBernoulliPosterior",
    "fit_conditional_bernoulli_map",
    "fixed_cardinality_covariance",
    "frequency_fixed_k_log_probability",
    "symbolic_fixed_cardinality_marginals",
    "symbolic_log_elementary_symmetric",
    "uniform_fixed_k_log_probability",
]
