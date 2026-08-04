from __future__ import annotations

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
    _validate_exogenous,
    _validate_observations,
)
from loto.probabilistic.models._dglm_state import MultinomialDGLMState


def _predict_one(mean: FloatArray, feature: FloatArray, classes: int) -> FloatArray:
    coefficients = mean.reshape(classes - 1, feature.size)
    return _softmax_reference(coefficients @ feature)


def _update_one(
    mean: FloatArray,
    covariance: FloatArray,
    *,
    feature: FloatArray,
    observed: int,
    classes: int,
    observation_jitter: float,
    covariance_floor: float,
) -> tuple[FloatArray, FloatArray, float, float]:
    probabilities = _predict_one(mean, feature, classes)
    non_reference = probabilities[:-1]
    response = np.zeros(classes - 1, dtype=np.float64)
    if observed < classes - 1:
        response[observed] = 1.0
    weight = np.diag(non_reference) - np.outer(non_reference, non_reference)
    weight += np.eye(classes - 1, dtype=np.float64) * observation_jitter
    jacobian = np.zeros((classes - 1, mean.size), dtype=np.float64)
    state_dim = feature.size
    for category in range(classes - 1):
        start = category * state_dim
        jacobian[category, start : start + state_dim] = feature
    prior_precision = np.linalg.inv(covariance)
    posterior_precision = prior_precision + jacobian.T @ weight @ jacobian
    posterior_precision = 0.5 * (posterior_precision + posterior_precision.T)
    condition = float(np.linalg.cond(posterior_precision))
    if not np.isfinite(condition) or condition > 1e14:
        raise ValueError("DGLM_FILTER_DIVERGED: posterior precision is singular or ill-conditioned")
    updated_covariance = np.linalg.inv(posterior_precision)
    score = jacobian.T @ (response - non_reference)
    updated_mean = mean + updated_covariance @ score
    updated_covariance, jitter = _ensure_psd(updated_covariance, covariance_floor)
    if not np.isfinite(updated_mean).all():
        raise ValueError("DGLM_FILTER_DIVERGED: state mean contains non-finite values")
    return updated_mean, updated_covariance, jitter, condition


def _advance_one(
    mean: FloatArray,
    covariance: FloatArray,
    *,
    evolution: FloatArray,
    discount_factor: float,
    covariance_floor: float,
    max_state_variance: float,
) -> tuple[FloatArray, FloatArray, float]:
    evolved_mean = evolution @ mean
    evolved_covariance = evolution @ covariance @ evolution.T
    evolved_covariance /= discount_factor
    evolved_covariance, jitter = _ensure_psd(evolved_covariance, covariance_floor)
    if float(np.diag(evolved_covariance).max()) > max_state_variance:
        raise ValueError("DGLM_FILTER_DIVERGED: state variance exceeded configured maximum")
    return evolved_mean, evolved_covariance, jitter


def fit_multinomial_dglm(
    y: np.ndarray,
    *,
    game: str,
    classes: int,
    config: Any,
    seed: int,
    exogenous: np.ndarray | None = None,
    initial_state: MultinomialDGLMState | None = None,
) -> MultinomialDGLMState:
    values = _validate_observations(y, classes)
    exogenous_values = _validate_exogenous(exogenous, len(values))
    positions = values.shape[1]
    seasonal_periods = tuple(float(item) for item in config.dglm_seasonal_periods)
    include_trend = bool(config.dglm_include_trend)
    exogenous_dim = 0 if exogenous_values is None else exogenous_values.shape[1]
    state_names, state_evolution = _state_structure(
        include_trend=include_trend,
        seasonal_periods=seasonal_periods,
        exogenous_dim=exogenous_dim,
    )
    flat_evolution = _block_diagonal(state_evolution, classes - 1)
    flat_dim = (classes - 1) * len(state_names)

    if initial_state is None:
        current_step = 0
        state_mean = np.zeros((positions, flat_dim), dtype=np.float64)
        state_covariance = np.repeat(
            np.eye(flat_dim, dtype=np.float64)[None, :, :], positions, axis=0
        )
        state_covariance *= float(config.dglm_prior_variance)
        history: list[FloatArray] = []
        update_history: list[NDArray[np.bool_]] = []
        max_covariance_jitter = 0.0
        max_condition = 0.0
    else:
        if initial_state.classes != classes or initial_state.positions != positions:
            raise ValueError("initial DGLM state classes/positions do not match observations")
        if initial_state.state_names != state_names:
            raise ValueError("initial DGLM state structure does not match current configuration")
        current_step = initial_state.current_step
        state_mean = initial_state.state_mean.copy()
        state_covariance = initial_state.state_covariance.copy()
        history = [row.copy() for row in initial_state.one_step_probabilities]
        update_history = [row.copy() for row in initial_state.update_applied]
        max_covariance_jitter = initial_state.max_covariance_jitter
        max_condition = initial_state.max_innovation_condition

    for offset, row in enumerate(values):
        step = current_step + offset
        exogenous_row = None if exogenous_values is None else exogenous_values[offset]
        feature = _feature_vector(
            step=step,
            include_trend=include_trend,
            seasonal_periods=seasonal_periods,
            exogenous=exogenous_row,
        )
        predictions = np.vstack(
            [_predict_one(state_mean[position], feature, classes) for position in range(positions)]
        )
        history.append(predictions)
        applied = np.zeros(positions, dtype=bool)
        for position in range(positions):
            observation = row[position]
            if np.isfinite(observation):
                updated = _update_one(
                    state_mean[position],
                    state_covariance[position],
                    feature=feature,
                    observed=int(observation),
                    classes=classes,
                    observation_jitter=float(config.dglm_observation_jitter),
                    covariance_floor=float(config.dglm_covariance_floor),
                )
                state_mean[position], state_covariance[position], jitter, condition = updated
                max_covariance_jitter = max(max_covariance_jitter, jitter)
                max_condition = max(max_condition, condition)
                applied[position] = True
        update_history.append(applied)
        for position in range(positions):
            advanced = _advance_one(
                state_mean[position],
                state_covariance[position],
                evolution=flat_evolution,
                discount_factor=float(config.dglm_discount_factor),
                covariance_floor=float(config.dglm_covariance_floor),
                max_state_variance=float(config.dglm_max_state_variance),
            )
            state_mean[position], state_covariance[position], jitter = advanced
            max_covariance_jitter = max(max_covariance_jitter, jitter)

    return MultinomialDGLMState(
        model_id=MODEL_ID,
        game=game,
        classes=classes,
        positions=positions,
        state_names=state_names,
        include_trend=include_trend,
        seasonal_periods=seasonal_periods,
        exogenous_dim=exogenous_dim,
        discount_factor=float(config.dglm_discount_factor),
        observation_jitter=float(config.dglm_observation_jitter),
        covariance_floor=float(config.dglm_covariance_floor),
        current_step=current_step + len(values),
        state_mean=state_mean,
        state_covariance=state_covariance,
        one_step_probabilities=np.asarray(history, dtype=np.float64),
        update_applied=np.asarray(update_history, dtype=bool),
        max_covariance_jitter=max_covariance_jitter,
        max_innovation_condition=max_condition,
        seed=seed,
        metadata={
            "inference": "sequential_extended_kalman_laplace",
            "observation_order": "predict_before_update",
            "discount_evolution": True,
            "exogenous_enabled": exogenous_dim > 0,
        },
    )
