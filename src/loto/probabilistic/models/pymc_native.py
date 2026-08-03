from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

PYMC_NATIVE_MODEL_IDS = frozenset(
    {
        "pp-empirical-bayes-dirichlet",
        "pp-dirichlet-multinomial",
        "pp-beta-binomial-position",
        "pp-beta-binomial-candidate",
        "pp-hierarchical-dirichlet-digits",
        "pp-hierarchical-dirichlet-games",
        "pp-multinomial-logit-normal",
        "pp-multinomial-logit-laplace",
        "pp-multinomial-logit-horseshoe",
        "pp-multinomial-logit-regularized-horseshoe",
        "pp-multinomial-probit",
        "pp-ordinal-cumulative-logit",
        "pp-ordinal-adjacent-category",
        "pp-ordinal-continuation-ratio",
        "pp-bayesian-spline-categorical",
        "pp-bayesian-gam-categorical",
        "pp-gp-categorical",
        "pp-dynamic-dirichlet-discount",
        "pp-logistic-normal-random-walk",
        "pp-local-level-categorical",
        "pp-local-linear-trend-categorical",
        "pp-dynamic-regression-categorical",
        "pp-dynamic-horseshoe-categorical",
        "pp-single-changepoint-categorical",
        "pp-multiple-changepoint-categorical",
        "pp-hmm-categorical",
        "pp-seasonal-harmonic-categorical",
        "pp-gaussian-process-time-varying-logit",
        "pp-poisson-candidate-count",
        "pp-negative-binomial-candidate-count",
        "pp-zero-inflated-poisson-count",
        "pp-zero-inflated-negative-binomial-count",
        "pp-beta-binomial-overdispersed",
        "pp-multinomial-logistic-normal-count",
        "pp-poisson-lognormal-count",
        "pp-hurdle-count",
        "pp-finite-mixture-categorical",
        "pp-mixture-of-experts-categorical",
        "pp-latent-class-categorical",
        "pp-dirichlet-process-categorical",
        "pp-bayesian-kernel-mixture",
        "pp-bayesian-model-averaging",
        "pp-dynamic-model-averaging",
        "pp-bayesian-beta-calibration",
        "pp-bayesian-dirichlet-calibration",
        "pp-bayesian-temperature-calibration",
    }
)

from loto.probabilistic.models.native_common import (
    base_probability_bank,
    bounded_training_data,
    categorical_design,
)


@dataclass(frozen=True)
class PyMCGraph:
    model: Any
    probability_variable: str = "next_probabilities"
    graph_id: str = ""
    metadata: dict[str, Any] | None = None


def _pm_modules() -> tuple[Any, Any]:
    import pymc as pm  # type: ignore
    import pytensor.tensor as pt  # type: ignore

    return pm, pt


def _softmax(pm: Any, value: Any) -> Any:
    return pm.math.softmax(value, axis=-1)


def _flatten(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(y, dtype=int)
    if values.ndim == 1:
        values = values[:, None]
    position_index = np.tile(np.arange(values.shape[1], dtype=int), len(values))
    return values.reshape(-1), position_index


def _observe_categorical(
    pm: Any, probabilities: Any, y: np.ndarray, name: str = "observed"
) -> None:
    observed, _ = _flatten(y)
    pm.Categorical(name, p=probabilities, observed=observed)


def _categorical_probability_rows(prob_by_position: Any, y: np.ndarray) -> Any:
    _, position_index = _flatten(y)
    return prob_by_position[position_index]


def _regression_prior(pm: Any, pt: Any, model_id: str, shape: tuple[int, ...]) -> Any:
    if model_id == "pp-multinomial-logit-laplace":
        return pm.Laplace("beta", mu=0.0, b=0.5, shape=shape)
    if model_id in {"pp-multinomial-logit-horseshoe", "pp-dynamic-horseshoe-categorical"}:
        tau = pm.HalfCauchy("tau", beta=0.5)
        lam = pm.HalfCauchy("lambda", beta=1.0, shape=shape)
        z = pm.Normal("beta_z", 0.0, 1.0, shape=shape)
        return pm.Deterministic("beta", z * tau * lam)
    if model_id == "pp-multinomial-logit-regularized-horseshoe":
        tau = pm.HalfCauchy("tau", beta=0.5)
        lam = pm.HalfCauchy("lambda", beta=1.0, shape=shape)
        slab = pm.InverseGamma("slab_variance", alpha=2.0, beta=8.0)
        lam_tilde = pt.sqrt(slab * lam**2 / (slab + tau**2 * lam**2))
        z = pm.Normal("beta_z", 0.0, 1.0, shape=shape)
        return pm.Deterministic("beta", z * tau * lam_tilde)
    return pm.Normal("beta", mu=0.0, sigma=0.75, shape=shape)


def _build_empirical_bayes(pm: Any, y: np.ndarray, classes: int, prior: float) -> Any:
    positions = y.shape[1]
    base = np.full(classes, prior, dtype=float)
    concentration = pm.LogNormal("concentration", mu=np.log(max(prior, 0.2)), sigma=0.8)
    p = pm.Dirichlet("p", a=concentration * base, shape=(positions, classes))
    _observe_categorical(pm, _categorical_probability_rows(p, y), y)
    return p


def _build_dirichlet_multinomial(pm: Any, y: np.ndarray, classes: int, prior: float) -> Any:
    totals = np.asarray(y, dtype=int).sum(axis=1)
    p = pm.Dirichlet("p", a=np.full(classes, prior))
    pm.Multinomial("observed", n=totals, p=p, observed=np.asarray(y, dtype=int))
    return p[None, :]


def _build_beta_binomial(
    pm: Any,
    y: np.ndarray,
    classes: int,
    prior: float,
    *,
    overdispersed: bool,
    position_mode: bool,
) -> Any:
    values = np.asarray(y, dtype=int)
    if values.ndim == 1:
        values = values[:, None]
    if position_mode:
        # select_position_inclusion arrives as one zero-based selected value per position.
        # Expand it to a binary position x candidate incidence tensor before applying
        # independent Beta-Binomial/Binomial likelihoods.
        binary = np.zeros((values.shape[0], values.shape[1], classes), dtype=int)
        row = np.arange(values.shape[0])[:, None]
        position = np.arange(values.shape[1])[None, :]
        binary[row, position, values] = 1
        probability_shape = (values.shape[1], classes)
    else:
        binary = values
        probability_shape = (values.shape[1],)

    if overdispersed:
        mean = pm.Beta("mean", alpha=prior, beta=prior, shape=probability_shape)
        concentration = pm.Gamma("concentration", alpha=2.0, beta=0.2)
        alpha = mean * concentration
        beta = (1.0 - mean) * concentration
        pm.BetaBinomial("observed", alpha=alpha, beta=beta, n=1, observed=binary)
        probability = mean
    else:
        probability = pm.Beta(
            "inclusion_probability", alpha=prior, beta=prior, shape=probability_shape
        )
        pm.Binomial("observed", n=1, p=probability, observed=binary)
    probability = probability / probability.sum(axis=-1, keepdims=True)
    return probability if position_mode else probability[None, :]


def _build_hierarchical(pm: Any, y: np.ndarray, classes: int, prior: float, model_id: str) -> Any:
    positions = y.shape[1]
    global_probability = pm.Dirichlet("global_probability", a=np.full(classes, prior))
    pooling = pm.Gamma("pooling_concentration", alpha=2.0, beta=0.1)
    if model_id == "pp-hierarchical-dirichlet-games":
        game_probability = pm.Dirichlet("game_probability", a=pooling * global_probability)
        local_pooling = pm.Gamma("position_pooling", alpha=2.0, beta=0.1)
        p = pm.Dirichlet("p", a=local_pooling * game_probability, shape=(positions, classes))
    else:
        p = pm.Dirichlet("p", a=pooling * global_probability, shape=(positions, classes))
    _observe_categorical(pm, _categorical_probability_rows(p, y), y)
    return p


def _build_categorical_regression(
    pm: Any,
    pt: Any,
    y: np.ndarray,
    classes: int,
    model_id: str,
    *,
    degree: int = 2,
    harmonics: int = 1,
) -> Any:
    positions = y.shape[1]
    X, X_next = categorical_design(y, classes, degree=degree, harmonics=harmonics)
    observed, position_index = _flatten(y)
    X_rows = np.repeat(X, positions, axis=0)
    features = X.shape[1]
    intercept = pm.Normal("intercept", 0.0, 1.0, shape=(positions, classes))
    beta = _regression_prior(pm, pt, model_id, (positions, features, classes))
    logits = intercept[position_index] + pt.sum(beta[position_index] * X_rows[:, :, None], axis=1)
    if model_id == "pp-multinomial-probit":
        positive = 0.5 * (1.0 + pt.erf(logits / np.sqrt(2.0)))
        probabilities = positive / positive.sum(axis=-1, keepdims=True)
    else:
        probabilities = _softmax(pm, logits)
    pm.Categorical("observed", p=probabilities, observed=observed)
    next_logits = intercept + pt.sum(beta * X_next[None, :, None], axis=1)
    if model_id == "pp-multinomial-probit":
        next_positive = 0.5 * (1.0 + pt.erf(next_logits / np.sqrt(2.0)))
        return next_positive / next_positive.sum(axis=-1, keepdims=True)
    return _softmax(pm, next_logits)


def _ordered_cutpoints(pm: Any, positions: int, classes: int) -> Any:
    transform = pm.distributions.transforms.ordered
    init = np.tile(np.linspace(-2.0, 2.0, classes - 1), (positions, 1))
    return pm.Normal(
        "cutpoints",
        mu=init,
        sigma=1.0,
        shape=(positions, classes - 1),
        transform=transform,
        initval=init,
    )


def _build_ordinal(pm: Any, pt: Any, y: np.ndarray, classes: int, model_id: str) -> Any:
    positions = y.shape[1]
    X, X_next = categorical_design(y, classes, degree=2, harmonics=1)
    observed, position_index = _flatten(y)
    X_rows = np.repeat(X, positions, axis=0)
    beta = pm.Normal("beta", 0.0, 0.8, shape=(positions, X.shape[1]))
    intercept = pm.Normal("intercept", 0.0, 1.0, shape=positions)
    eta = intercept[position_index] + pt.sum(beta[position_index] * X_rows, axis=1)
    cutpoints = _ordered_cutpoints(pm, positions, classes)
    local_cutpoints = cutpoints[position_index]
    if model_id == "pp-ordinal-cumulative-logit":
        pm.OrderedLogistic("observed", eta=eta, cutpoints=local_cutpoints, observed=observed)
        next_eta = intercept + pt.sum(beta * X_next[None, :], axis=1)
        lower = pm.math.sigmoid(cutpoints - next_eta[:, None])
        probability_parts = [lower[:, :1], lower[:, 1:] - lower[:, :-1], 1.0 - lower[:, -1:]]
        return pt.concatenate(probability_parts, axis=1)
    adjacent = eta[:, None] - local_cutpoints
    if model_id == "pp-ordinal-adjacent-category":
        category_logits = pt.concatenate(
            [pt.zeros((adjacent.shape[0], 1)), pt.cumsum(adjacent, axis=1)], axis=1
        )
        probabilities = _softmax(pm, category_logits)
        pm.Categorical("observed", p=probabilities, observed=observed)
        next_eta = intercept + pt.sum(beta * X_next[None, :], axis=1)
        next_adjacent = next_eta[:, None] - cutpoints
        next_logits = pt.concatenate(
            [pt.zeros((positions, 1)), pt.cumsum(next_adjacent, axis=1)], axis=1
        )
        return _softmax(pm, next_logits)
    # Continuation-ratio: conditional probability of stopping in each category.
    hazards = pm.math.sigmoid(adjacent)
    survival_before = pt.concatenate(
        [pt.ones((hazards.shape[0], 1)), pt.cumprod(1.0 - hazards, axis=1)[:, :-1]], axis=1
    )
    probabilities = pt.concatenate(
        [hazards * survival_before, pt.cumprod(1.0 - hazards, axis=1)[:, -1:]], axis=1
    )
    pm.Categorical("observed", p=probabilities, observed=observed)
    next_eta = intercept + pt.sum(beta * X_next[None, :], axis=1)
    next_hazards = pm.math.sigmoid(next_eta[:, None] - cutpoints)
    next_survival = pt.concatenate(
        [pt.ones((positions, 1)), pt.cumprod(1.0 - next_hazards, axis=1)[:, :-1]], axis=1
    )
    return pt.concatenate(
        [next_hazards * next_survival, pt.cumprod(1.0 - next_hazards, axis=1)[:, -1:]],
        axis=1,
    )


def _build_gp(pm: Any, pt: Any, y: np.ndarray, classes: int, *, time_varying: bool) -> Any:
    positions = y.shape[1]
    n = len(y)
    time = np.linspace(-1.0, 1.0, n)[:, None]
    length_scale = pm.LogNormal("length_scale", mu=-0.5, sigma=0.7)
    amplitude = pm.HalfNormal("amplitude", sigma=1.0)
    distance = (time - time.T) ** 2
    covariance = amplitude**2 * pt.exp(-0.5 * distance / length_scale**2)
    covariance = covariance + pt.eye(n) * 1e-5
    f = pm.MvNormal("latent_gp", mu=pt.zeros(n), cov=covariance, shape=(positions, classes, n))
    logits_rows = f.dimshuffle(2, 0, 1).reshape((n * positions, classes))
    observed, _ = _flatten(y)
    pm.Categorical("observed", p=_softmax(pm, logits_rows), observed=observed)
    innovation_scale = pm.HalfNormal("forecast_innovation", sigma=0.3 if time_varying else 0.15)
    next_logits = pm.Normal(
        "next_logits", mu=f[:, :, -1], sigma=innovation_scale, shape=(positions, classes)
    )
    return _softmax(pm, next_logits)


def _build_dynamic_dirichlet(
    pm: Any,
    pt: Any,
    y: np.ndarray,
    classes: int,
    prior: float,
    discount_center: float,
) -> Any:
    positions = y.shape[1]
    observed, position_index = _flatten(y)
    # Learn a discount close to the configured center while retaining a proper
    # Dirichlet prior. The weighted likelihood gives recent draws more influence
    # without using the observations twice to construct a posterior parameter.
    concentration = 40.0
    alpha_discount = max(discount_center * concentration, 1e-3)
    beta_discount = max((1.0 - discount_center) * concentration, 1e-3)
    discount = pm.Beta("discount", alpha=alpha_discount, beta=beta_discount)
    p = pm.Dirichlet("p", a=np.full(classes, prior), shape=(positions, classes))
    row_age = np.repeat(np.arange(len(y) - 1, -1, -1, dtype=float), positions)
    weights = discount**row_age
    selected = p[position_index, observed]
    pm.Potential(
        "discounted_categorical_likelihood",
        pt.sum(weights * pt.log(pt.maximum(selected, 1e-15))),
    )
    return p


def _build_dynamic(pm: Any, pt: Any, y: np.ndarray, classes: int, model_id: str) -> Any:
    positions = y.shape[1]
    n = len(y)
    observed, _ = _flatten(y)
    sigma = pm.HalfNormal("state_sigma", sigma=0.5)
    if model_id == "pp-local-linear-trend-categorical":
        slope = pm.GaussianRandomWalk("slope", sigma=sigma, shape=(positions, classes, n))
        level_noise = pm.GaussianRandomWalk(
            "level_noise", sigma=sigma, shape=(positions, classes, n)
        )
        logits_state = pm.Deterministic("logits_state", level_noise + pt.cumsum(slope, axis=-1))
        next_logits = logits_state[:, :, -1] + slope[:, :, -1]
    elif model_id in {"pp-dynamic-regression-categorical", "pp-dynamic-horseshoe-categorical"}:
        X, X_next = categorical_design(y, classes, degree=2, harmonics=1)
        features = X.shape[1]
        if model_id == "pp-dynamic-horseshoe-categorical":
            tau = pm.HalfCauchy("tau", beta=0.5)
            lam = pm.HalfCauchy("lambda", beta=1.0, shape=(positions, features, classes))
            beta_base = pm.Normal("beta_base", 0.0, 1.0, shape=(positions, features, classes))
            beta_base = pm.Deterministic("beta", beta_base * tau * lam)
        else:
            beta_base = pm.Normal("beta", 0.0, 0.5, shape=(positions, features, classes))
        state = pm.GaussianRandomWalk("state", sigma=sigma, shape=(positions, classes, n))
        fixed = pt.sum(beta_base[:, :, :, None] * X.T[None, :, None, :], axis=1)
        logits_state = fixed + state
        next_logits = pt.sum(beta_base * X_next[None, :, None], axis=1) + state[:, :, -1]
    elif model_id == "pp-seasonal-harmonic-categorical":
        X, X_next = categorical_design(y, classes, degree=1, harmonics=3)
        beta = pm.Normal("beta", 0.0, 0.5, shape=(positions, X.shape[1], classes))
        logits_state = pt.sum(beta[:, :, :, None] * X.T[None, :, None, :], axis=1)
        next_logits = pt.sum(beta * X_next[None, :, None], axis=1)
    else:
        logits_state = pm.GaussianRandomWalk(
            "logits_state", sigma=sigma, shape=(positions, classes, n)
        )
        if model_id == "pp-local-level-categorical":
            next_logits = logits_state[:, :, -1]
        else:
            innovation = pm.Normal("next_innovation", 0.0, sigma, shape=(positions, classes))
            next_logits = logits_state[:, :, -1] + innovation
    rows = logits_state.dimshuffle(2, 0, 1).reshape((n * positions, classes))
    pm.Categorical("observed", p=_softmax(pm, rows), observed=observed)
    return _softmax(pm, next_logits)


def _build_changepoint(pm: Any, pt: Any, y: np.ndarray, classes: int, model_id: str) -> Any:
    positions = y.shape[1]
    n = len(y)
    observed, _ = _flatten(y)
    pre = pm.Normal("pre_logits", 0.0, 1.0, shape=(positions, classes))
    post = pm.Normal("post_logits", 0.0, 1.0, shape=(positions, classes))
    time = pt.arange(n)
    if model_id == "pp-single-changepoint-categorical":
        tau = pm.DiscreteUniform("tau", lower=1, upper=max(1, n - 1))
        state = pt.switch(time[:, None, None] < tau, pre[None, :, :], post[None, :, :])
        next_logits = post
    else:
        middle = pm.Normal("middle_logits", 0.0, 1.0, shape=(positions, classes))
        tau1 = pm.DiscreteUniform("tau1", lower=1, upper=max(1, n - 2))
        tau2 = pm.DiscreteUniform("tau2", lower=2, upper=max(2, n - 1))
        pm.Potential("ordered_change_points", pt.switch(tau2 > tau1, 0.0, -np.inf))
        state = pt.switch(
            time[:, None, None] < tau1,
            pre[None, :, :],
            pt.switch(time[:, None, None] < tau2, middle[None, :, :], post[None, :, :]),
        )
        next_logits = post
    rows = state.reshape((n * positions, classes))
    pm.Categorical("observed", p=_softmax(pm, rows), observed=observed)
    return _softmax(pm, next_logits)


def _build_hmm(pm: Any, pt: Any, y: np.ndarray, classes: int) -> Any:
    # Shared latent regime across positions, position-specific emission distributions.
    positions = y.shape[1]
    n = len(y)
    regimes = 3
    transition = pm.Dirichlet(
        "transition", a=np.ones(regimes) + np.eye(regimes) * 3.0, shape=(regimes, regimes)
    )
    emission = pm.Dirichlet("emission", a=np.ones(classes), shape=(regimes, positions, classes))
    initial = pm.Dirichlet("initial", a=np.ones(regimes))
    states = [pm.Categorical("state_0", p=initial)]
    pm.Categorical("observed_0", p=emission[states[0]], observed=y[0])
    for index in range(1, n):
        state = pm.Categorical(f"state_{index}", p=transition[states[-1]])
        states.append(state)
        pm.Categorical(f"observed_{index}", p=emission[state], observed=y[index])
    next_regime = transition[states[-1]]
    return pt.sum(next_regime[:, None, None] * emission, axis=0)


def _normalized_rate(rate: Any) -> Any:
    return rate[None, :] / rate.sum()


def _build_counts(pm: Any, pt: Any, y: np.ndarray, model_id: str, prior: float) -> Any:
    values = np.asarray(y, dtype=int)
    classes = values.shape[1]
    if model_id == "pp-beta-binomial-overdispersed":
        return _build_beta_binomial(
            pm, values, values.shape[1], prior, overdispersed=True, position_mode=False
        )
    if model_id == "pp-multinomial-logistic-normal-count":
        logits = pm.Normal("logits", 0.0, 1.0, shape=classes)
        p = _softmax(pm, logits)
        pm.Multinomial("observed", n=values.sum(axis=1), p=p, observed=values)
        return p[None, :]
    if model_id == "pp-poisson-lognormal-count":
        global_scale = pm.HalfNormal("global_scale", sigma=1.0)
        log_rate = pm.Normal("log_rate", mu=0.0, sigma=global_scale, shape=classes)
        rate = pm.Deterministic("rate", pt.exp(log_rate))
        pm.Poisson("observed", mu=rate, observed=values)
        return _normalized_rate(rate)
    rate = pm.Gamma("rate", alpha=max(prior, 0.2), beta=0.2, shape=classes)
    if model_id == "pp-poisson-candidate-count":
        pm.Poisson("observed", mu=rate, observed=values)
    elif model_id == "pp-negative-binomial-candidate-count":
        alpha = pm.HalfNormal("overdispersion", sigma=5.0)
        pm.NegativeBinomial("observed", mu=rate, alpha=alpha, observed=values)
    elif model_id == "pp-zero-inflated-poisson-count":
        psi = pm.Beta("nonzero_probability", alpha=2.0, beta=2.0, shape=classes)
        pm.ZeroInflatedPoisson("observed", psi=psi, mu=rate, observed=values)
        rate = psi * rate
    elif model_id == "pp-zero-inflated-negative-binomial-count":
        psi = pm.Beta("nonzero_probability", alpha=2.0, beta=2.0, shape=classes)
        alpha = pm.HalfNormal("overdispersion", sigma=5.0)
        pm.ZeroInflatedNegativeBinomial("observed", psi=psi, mu=rate, alpha=alpha, observed=values)
        rate = psi * rate
    elif model_id == "pp-hurdle-count":
        psi = pm.Beta("positive_probability", alpha=2.0, beta=2.0, shape=classes)
        zero = values == 0
        pm.Bernoulli("zero_indicator", p=1.0 - psi, observed=zero.astype(int))
        positive = np.maximum(values, 1)
        poisson = pm.Poisson.dist(mu=rate)
        log_norm = pt.log(-pt.expm1(-rate))
        pm.Potential(
            "positive_count_likelihood",
            pt.sum(pt.switch(zero, 0.0, pm.logp(poisson, positive) - log_norm)),
        )
        rate = psi * rate / pt.maximum(1.0 - pt.exp(-rate), 1e-9)
    else:
        raise KeyError(model_id)
    return _normalized_rate(rate)


def _stick_breaking(pt: Any, v: Any) -> Any:
    remaining = pt.concatenate([pt.ones(1), pt.cumprod(1.0 - v)])
    return pt.concatenate([v, pt.ones(1)]) * remaining


def _build_mixture(pm: Any, pt: Any, y: np.ndarray, classes: int, model_id: str) -> Any:
    positions = y.shape[1]
    components_count = 4
    if model_id == "pp-bayesian-kernel-mixture":
        centers = np.linspace(0, classes - 1, components_count)
        grid = np.arange(classes)
        kernels = np.exp(-0.5 * ((grid[None, :] - centers[:, None]) / 1.25) ** 2)
        kernels /= kernels.sum(axis=1, keepdims=True)
        weights = pm.Dirichlet(
            "kernel_weights", a=np.ones(components_count), shape=(positions, components_count)
        )
        p = pt.dot(weights, kernels)
        _observe_categorical(pm, _categorical_probability_rows(p, y), y)
        return p
    if model_id == "pp-dirichlet-process-categorical":
        v = pm.Beta(
            "stick", alpha=1.0, beta=pm.Gamma("dp_alpha", 2.0, 1.0), shape=components_count - 1
        )
        weights = pm.Deterministic("weights", _stick_breaking(pt, v))
    else:
        weights = pm.Dirichlet("weights", a=np.ones(components_count))
    components = pm.Dirichlet(
        "components", a=np.ones(classes), shape=(components_count, positions, classes)
    )
    if model_id == "pp-mixture-of-experts-categorical":
        n = len(y)
        time = np.linspace(-1.0, 1.0, n)
        gate_intercept = pm.Normal("gate_intercept", 0.0, 1.0, shape=components_count)
        gate_slope = pm.Normal("gate_slope", 0.0, 1.0, shape=components_count)
        gate = _softmax(pm, gate_intercept[None, :] + time[:, None] * gate_slope[None, :])
        probabilities = pt.sum(gate[:, :, None, None] * components[None, :, :, :], axis=1)
        observed, _ = _flatten(y)
        pm.Categorical(
            "observed", p=probabilities.reshape((n * positions, classes)), observed=observed
        )
        next_gate = _softmax(pm, gate_intercept + 1.05 * gate_slope)
        return pt.sum(next_gate[:, None, None] * components, axis=0)
    p = pt.sum(weights[:, None, None] * components, axis=0)
    _observe_categorical(pm, _categorical_probability_rows(p, y), y)
    return p


def _build_meta(
    pm: Any,
    pt: Any,
    y: np.ndarray,
    classes: int,
    model_id: str,
    prior: float,
    window: int,
    discount: float,
) -> Any:
    bank = base_probability_bank(y, classes, prior=prior, window=window, discount=discount)
    positions = y.shape[1]
    observed, position_index = _flatten(y)
    if model_id == "pp-bayesian-model-averaging":
        weights = pm.Dirichlet("model_weights", a=np.ones(bank.shape[0]))
        p = pt.sum(weights[:, None, None] * bank, axis=0)
    elif model_id == "pp-dynamic-model-averaging":
        n = len(y)
        weight_logits = pm.GaussianRandomWalk("weight_logits", sigma=0.3, shape=(n, bank.shape[0]))
        weights = _softmax(pm, weight_logits)
        p_rows = pt.sum(weights[:, :, None, None] * bank[None, :, :, :], axis=1)
        pm.Categorical(
            "observed",
            p=p_rows.reshape((n * positions, classes)),
            observed=observed,
        )
        next_weights = _softmax(pm, weight_logits[-1])
        return pt.sum(next_weights[:, None, None] * bank, axis=0)
    else:
        base = np.clip(bank[1], 1e-8, 1.0 - 1e-8)
        if model_id == "pp-bayesian-beta-calibration":
            a = pm.LogNormal("a", mu=0.0, sigma=0.5)
            b = pm.LogNormal("b", mu=0.0, sigma=0.5)
            c = pm.Normal("c", 0.0, 0.5, shape=(positions, classes))
            logits = a * np.log(base) - b * np.log1p(-base) + c
            p = _softmax(pm, logits)
        elif model_id == "pp-bayesian-dirichlet-calibration":
            delta = pm.Normal("calibration_delta", 0.0, 0.15, shape=(classes, classes))
            bias = pm.Normal("calibration_bias", 0.0, 0.2, shape=classes)
            transform = pt.eye(classes) + delta
            logits = pt.dot(np.log(base), transform) + bias
            p = _softmax(pm, logits)
        elif model_id == "pp-bayesian-temperature-calibration":
            temperature = pm.LogNormal("temperature", mu=0.0, sigma=0.35)
            p = _softmax(pm, np.log(base) / temperature)
        else:
            raise KeyError(model_id)
    pm.Categorical("observed", p=p[position_index], observed=observed)
    return p


def build_pymc_graph(
    spec: Any,
    *,
    y: np.ndarray,
    classes: int,
    target_mode: str,
    geometry: Any,
    config: Any,
    seed: int,
) -> PyMCGraph:
    pm, pt = _pm_modules()
    values = bounded_training_data(y, config.native_max_train_rows).astype(int)
    if values.ndim == 1:
        values = values[:, None]
    model_id = spec.model_id
    if model_id not in PYMC_NATIVE_MODEL_IDS:
        raise KeyError(f"no pymc primary graph for {model_id}")
    prior = float(config.prior_concentration)
    with pm.Model() as model:
        if model_id == "pp-empirical-bayes-dirichlet":
            p = _build_empirical_bayes(pm, values, classes, prior)
        elif model_id == "pp-dirichlet-multinomial":
            p = _build_dirichlet_multinomial(pm, values, classes, prior)
        elif model_id in {"pp-beta-binomial-position", "pp-beta-binomial-candidate"}:
            p = _build_beta_binomial(
                pm,
                values,
                classes,
                prior,
                overdispersed=False,
                position_mode=model_id == "pp-beta-binomial-position",
            )
        elif model_id in {"pp-hierarchical-dirichlet-digits", "pp-hierarchical-dirichlet-games"}:
            p = _build_hierarchical(pm, values, classes, prior, model_id)
        elif model_id in {
            "pp-multinomial-logit-normal",
            "pp-multinomial-logit-laplace",
            "pp-multinomial-logit-horseshoe",
            "pp-multinomial-logit-regularized-horseshoe",
            "pp-multinomial-probit",
        }:
            p = _build_categorical_regression(pm, pt, values, classes, model_id)
        elif model_id in {
            "pp-ordinal-cumulative-logit",
            "pp-ordinal-adjacent-category",
            "pp-ordinal-continuation-ratio",
        }:
            p = _build_ordinal(pm, pt, values, classes, model_id)
        elif model_id == "pp-bayesian-spline-categorical":
            p = _build_categorical_regression(
                pm, pt, values, classes, model_id, degree=4, harmonics=0
            )
        elif model_id == "pp-bayesian-gam-categorical":
            p = _build_categorical_regression(
                pm, pt, values, classes, model_id, degree=3, harmonics=3
            )
        elif model_id in {"pp-gp-categorical", "pp-gaussian-process-time-varying-logit"}:
            p = _build_gp(
                pm,
                pt,
                values,
                classes,
                time_varying=model_id.endswith("time-varying-logit"),
            )
        elif model_id == "pp-dynamic-dirichlet-discount":
            p = _build_dynamic_dirichlet(
                pm,
                pt,
                values,
                classes,
                prior,
                config.discount_factor,
            )
        elif model_id in {
            "pp-logistic-normal-random-walk",
            "pp-local-level-categorical",
            "pp-local-linear-trend-categorical",
            "pp-dynamic-regression-categorical",
            "pp-dynamic-horseshoe-categorical",
            "pp-seasonal-harmonic-categorical",
        }:
            p = _build_dynamic(pm, pt, values, classes, model_id)
        elif model_id in {
            "pp-single-changepoint-categorical",
            "pp-multiple-changepoint-categorical",
        }:
            p = _build_changepoint(pm, pt, values, classes, model_id)
        elif model_id == "pp-hmm-categorical":
            # Keep explicit discrete state space bounded for SMC smoke and audit runs.
            p = _build_hmm(pm, pt, values[-min(len(values), 80) :], classes)
        elif model_id in {
            "pp-poisson-candidate-count",
            "pp-negative-binomial-candidate-count",
            "pp-zero-inflated-poisson-count",
            "pp-zero-inflated-negative-binomial-count",
            "pp-beta-binomial-overdispersed",
            "pp-multinomial-logistic-normal-count",
            "pp-poisson-lognormal-count",
            "pp-hurdle-count",
        }:
            p = _build_counts(pm, pt, values, model_id, prior)
        elif model_id in {
            "pp-finite-mixture-categorical",
            "pp-mixture-of-experts-categorical",
            "pp-latent-class-categorical",
            "pp-dirichlet-process-categorical",
            "pp-bayesian-kernel-mixture",
        }:
            p = _build_mixture(pm, pt, values, classes, model_id)
        elif model_id in {
            "pp-bayesian-model-averaging",
            "pp-dynamic-model-averaging",
            "pp-bayesian-beta-calibration",
            "pp-bayesian-dirichlet-calibration",
            "pp-bayesian-temperature-calibration",
        }:
            p = _build_meta(
                pm,
                pt,
                values,
                classes,
                model_id,
                prior,
                config.rolling_window,
                config.discount_factor,
            )
        else:
            raise KeyError(f"no PyMC graph for {model_id}")
        pm.Deterministic("next_probabilities", p)
    return PyMCGraph(
        model=model,
        graph_id=spec.native_graph_id,
        metadata={
            "training_rows_used": len(values),
            "classes": classes,
            "positions": int(values.shape[1]),
            "seed": seed,
        },
    )
