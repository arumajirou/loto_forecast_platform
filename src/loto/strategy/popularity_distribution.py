"""Count-distribution popularity models with explicit uncertainty.

The existing weighted-ridge popularity surface remains the behavioural baseline. This module adds
sales-offset count models for *co-winner counts*. It never models or changes draw win probability.
Internal optimizer convergence is not an actionability decision; formal use still requires
chronological OOF, negative controls, calibration and the repository's promotion/evidence gates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom, poisson

from loto.game.geometry import GameGeometry
from loto.strategy.popularity import FEATURE_NAMES, combination_features

CountFamily = Literal["poisson", "negative_binomial"]


def _matrix(combinations: Sequence[Sequence[int]], geometry: GameGeometry) -> np.ndarray:
    if geometry.family != "select":
        raise ValueError("popularity count models are defined for select-family games only")
    return np.vstack([combination_features(values, geometry) for values in combinations])


def _positive_sales(sales: Sequence[float], n: int) -> np.ndarray:
    values = np.asarray(sales, dtype=float).ravel()
    if values.size != n:
        raise ValueError("sales must align with combinations")
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError("sales must be finite and strictly positive")
    return values


def _counts(winner_counts: Sequence[float], n: int) -> np.ndarray:
    values = np.asarray(winner_counts, dtype=float).ravel()
    if values.size != n:
        raise ValueError("winner_counts must align with combinations")
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("winner_counts must be finite and non-negative")
    if np.any(np.abs(values - np.rint(values)) > 1e-9):
        raise ValueError("winner_counts must be integer-valued")
    return np.rint(values).astype(int)


@dataclass(frozen=True)
class PopularityCountModel:
    game: str
    family: CountFamily
    coefficients: tuple[float, ...]
    feature_names: tuple[str, ...]
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]
    dispersion_alpha: float | None
    n_observations: int
    optimizer_success: bool
    optimizer_message: str
    objective_value: float
    ridge_lambda: float
    sales_offset: bool = True

    def _linear_predictor(self, features: np.ndarray, sales: np.ndarray) -> np.ndarray:
        x = np.atleast_2d(np.asarray(features, dtype=float))
        if x.shape[1] != len(self.feature_names):
            raise ValueError("feature width does not match fitted popularity model")
        mean = np.asarray(self.feature_mean, dtype=float)
        scale = np.asarray(self.feature_scale, dtype=float)
        standardised = (x - mean) / scale
        design = np.column_stack([np.ones(len(standardised)), standardised])
        beta = np.asarray(self.coefficients, dtype=float)
        eta = design @ beta + np.log(sales)
        return np.clip(eta, -30.0, 30.0)

    def predict_mean(
        self,
        combinations: Sequence[Sequence[int]],
        geometry: GameGeometry,
        *,
        sales: Sequence[float],
    ) -> np.ndarray:
        x = _matrix(combinations, geometry)
        s = _positive_sales(sales, len(x))
        return np.exp(self._linear_predictor(x, s))

    def predict_quantile(
        self,
        combinations: Sequence[Sequence[int]],
        geometry: GameGeometry,
        *,
        sales: Sequence[float],
        q: float,
    ) -> np.ndarray:
        if not 0.0 < q < 1.0:
            raise ValueError("q must be in (0, 1)")
        mu = self.predict_mean(combinations, geometry, sales=sales)
        if self.family == "poisson":
            return poisson.ppf(q, mu).astype(float)
        alpha = float(self.dispersion_alpha or 0.0)
        if alpha <= 0:
            raise ValueError("negative-binomial model requires positive dispersion_alpha")
        size = 1.0 / alpha
        probability = size / (size + mu)
        return nbinom.ppf(q, size, probability).astype(float)

    def prediction_record(
        self,
        combination: Sequence[int],
        geometry: GameGeometry,
        *,
        sales: float,
    ) -> dict[str, object]:
        combo = [int(value) for value in combination]
        geometry.validate_outcome(combo)
        mean = float(self.predict_mean([combo], geometry, sales=[sales])[0])
        q50 = float(self.predict_quantile([combo], geometry, sales=[sales], q=0.50)[0])
        q80 = float(self.predict_quantile([combo], geometry, sales=[sales], q=0.80)[0])
        q95 = float(self.predict_quantile([combo], geometry, sales=[sales], q=0.95)[0])
        return {
            "combination": combo,
            "expected_co_winners": mean,
            "q50_co_winners": q50,
            "q80_co_winners": q80,
            "q95_co_winners": q95,
            "family": self.family,
            "optimizer_success": self.optimizer_success,
            "actionable": False,
            "actionable_reason": (
                "model fit alone is insufficient; chronological OOF, negative controls and "
                "calibration evidence are required before recommendation"
            ),
            "win_probability": 1.0 / geometry.outcome_space,
            "win_probability_note": "identical for every legal combination; not improved here",
        }


def _poisson_objective(
    theta: np.ndarray,
    design: np.ndarray,
    counts: np.ndarray,
    offset: np.ndarray,
    ridge_lambda: float,
) -> float:
    eta = np.clip(design @ theta + offset, -30.0, 30.0)
    mu = np.exp(eta)
    penalty = ridge_lambda * float(np.sum(theta[1:] ** 2))
    return float(np.sum(mu - counts * eta + gammaln(counts + 1)) + penalty)


def _nb_objective(
    parameters: np.ndarray,
    design: np.ndarray,
    counts: np.ndarray,
    offset: np.ndarray,
    ridge_lambda: float,
) -> float:
    beta = parameters[:-1]
    alpha = math.exp(float(parameters[-1]))
    eta = np.clip(design @ beta + offset, -30.0, 30.0)
    mu = np.exp(eta)
    size = 1.0 / alpha
    log_probability = np.log(size / (size + mu))
    log_one_minus = np.log(mu / (size + mu))
    log_likelihood = (
        gammaln(counts + size)
        - gammaln(size)
        - gammaln(counts + 1)
        + size * log_probability
        + counts * log_one_minus
    )
    penalty = ridge_lambda * float(np.sum(beta[1:] ** 2))
    return float(-np.sum(log_likelihood) + penalty)


def fit_popularity_count_model(
    combinations: Sequence[Sequence[int]],
    winner_counts: Sequence[float],
    geometry: GameGeometry,
    *,
    sales: Sequence[float],
    family: CountFamily = "negative_binomial",
    ridge_lambda: float = 1e-4,
    max_iterations: int = 1000,
) -> PopularityCountModel:
    """Fit a Poisson or NB2 co-winner count model with a log-sales offset."""
    if family not in {"poisson", "negative_binomial"}:
        raise ValueError(f"unsupported count family: {family}")
    if ridge_lambda < 0:
        raise ValueError("ridge_lambda must be >= 0")
    x = _matrix(combinations, geometry)
    if len(x) <= x.shape[1] + 1:
        raise ValueError(f"need more than {x.shape[1] + 1} observations")
    y = _counts(winner_counts, len(x))
    s = _positive_sales(sales, len(x))
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale = np.where(scale <= 1e-12, 1.0, scale)
    standardised = (x - mean) / scale
    design = np.column_stack([np.ones(len(x)), standardised])
    offset = np.log(s)

    initial = np.zeros(design.shape[1], dtype=float)
    initial[0] = float(np.log((y.mean() + 0.1) / s.mean()))
    if family == "poisson":
        result = minimize(
            _poisson_objective,
            initial,
            args=(design, y, offset, ridge_lambda),
            method="L-BFGS-B",
            options={"maxiter": max_iterations},
        )
        beta = result.x
        alpha = None
    else:
        poisson_fit = minimize(
            _poisson_objective,
            initial,
            args=(design, y, offset, ridge_lambda),
            method="L-BFGS-B",
            options={"maxiter": max_iterations},
        )
        mu = np.exp(np.clip(design @ poisson_fit.x + offset, -30.0, 30.0))
        empirical_alpha = max(
            float(np.mean((y - mu) ** 2 - mu) / max(np.mean(mu**2), 1e-12)),
            1e-6,
        )
        nb_initial = np.concatenate([poisson_fit.x, [math.log(empirical_alpha)]])
        result = minimize(
            _nb_objective,
            nb_initial,
            args=(design, y, offset, ridge_lambda),
            method="L-BFGS-B",
            bounds=[(None, None)] * design.shape[1] + [(math.log(1e-8), math.log(1e4))],
            options={"maxiter": max_iterations},
        )
        beta = result.x[:-1]
        alpha = math.exp(float(result.x[-1]))

    if not np.isfinite(beta).all() or alpha is not None and not math.isfinite(alpha):
        raise RuntimeError("popularity count optimizer produced non-finite parameters")
    return PopularityCountModel(
        game=geometry.key,
        family=family,
        coefficients=tuple(float(value) for value in beta),
        feature_names=FEATURE_NAMES,
        feature_mean=tuple(float(value) for value in mean),
        feature_scale=tuple(float(value) for value in scale),
        dispersion_alpha=alpha,
        n_observations=len(x),
        optimizer_success=bool(result.success),
        optimizer_message=str(result.message),
        objective_value=float(result.fun),
        ridge_lambda=ridge_lambda,
    )
