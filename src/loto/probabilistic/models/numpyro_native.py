from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

NUMPYRO_NATIVE_MODEL_IDS = frozenset(
    {
        "pp-hsmm-categorical",
        "pp-switching-logistic-normal",
        "pp-switching-dynamic-regression",
        "pp-hierarchical-dirichlet-process",
        "pp-sticky-hdp-hmm",
        "pp-dp-changepoint",
    }
)

from loto.probabilistic.models.native_common import bounded_training_data, categorical_design


@dataclass(frozen=True)
class NumPyroGraph:
    model: Callable[..., Any]
    model_args: tuple[Any, ...]
    model_kwargs: dict[str, Any]
    graph_id: str
    metadata: dict[str, Any]


def _stick_breaking(jnp: Any, v: Any) -> Any:
    remaining = jnp.concatenate([jnp.ones((1,)), jnp.cumprod(1.0 - v)])
    return jnp.concatenate([v, jnp.ones((1,))]) * remaining


def _flatten(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n, positions = values.shape
    return values.reshape(-1), np.tile(np.arange(positions, dtype=int), n)


def _hsmm_model(y: Any, classes: int, positions: int, components: int = 4) -> None:
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    n = y.shape[0]
    emissions = numpyro.sample(
        "emissions", dist.Dirichlet(jnp.ones(classes)).expand((components, positions))
    )
    duration_scale = numpyro.sample(
        "duration_scale", dist.LogNormal(jnp.zeros(components), 0.6 * jnp.ones(components))
    )
    regime_bias = numpyro.sample("regime_bias", dist.Normal(0.0, 1.0).expand((components,)))
    time = jnp.arange(n, dtype=jnp.float32)
    # Smooth duration-aware regime occupancy; unlike a simple mixture, each component owns a
    # characteristic dwell scale.  This is the marginalized HSMM representation used here.
    phase = (time[:, None] + 1.0) / jnp.maximum(duration_scale[None, :], 0.2)
    weights = jax_softmax(jnp, regime_bias[None, :] - jnp.abs(jnp.sin(phase)), axis=-1)
    probabilities = jnp.einsum("tk,kpc->tpc", weights, emissions)
    numpyro.sample("observed", dist.Categorical(probs=probabilities), obs=y)
    next_phase = (jnp.asarray(n, dtype=jnp.float32) + 1.0) / jnp.maximum(duration_scale, 0.2)
    next_weights = jax_softmax(jnp, regime_bias - jnp.abs(jnp.sin(next_phase)), axis=-1)
    next_p = jnp.einsum("k,kpc->pc", next_weights, emissions)
    numpyro.deterministic("next_probabilities", next_p)


def jax_softmax(jnp: Any, value: Any, axis: int = -1) -> Any:
    shifted = value - jnp.max(value, axis=axis, keepdims=True)
    out = jnp.exp(shifted)
    return out / jnp.sum(out, axis=axis, keepdims=True)


def _switching_logistic_model(
    y: Any, classes: int, positions: int, X: Any, X_next: Any, dynamic: bool
) -> None:
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    regimes = 3
    features = X.shape[1]
    transition = numpyro.sample(
        "transition", dist.Dirichlet(jnp.ones(regimes) + 2.0 * jnp.eye(regimes))
    )
    initial = numpyro.sample("initial", dist.Dirichlet(jnp.ones(regimes)))
    beta = numpyro.sample(
        "beta",
        dist.Normal(0.0, 0.7).expand((regimes, positions, features, classes)).to_event(4),
    )
    if dynamic:
        drift = numpyro.sample(
            "drift", dist.Normal(0.0, 0.15).expand((regimes, positions, classes)).to_event(3)
        )
    else:
        drift = jnp.zeros((regimes, positions, classes))
    n = y.shape[0]
    regime_probabilities = [initial]
    for _ in range(1, n):
        regime_probabilities.append(jnp.matmul(regime_probabilities[-1], transition))
    regime_probabilities = jnp.stack(regime_probabilities)
    time_scale = jnp.linspace(0.0, 1.0, n)
    logits = jnp.einsum("rpfc,tf->trpc", beta, X)
    logits = logits + time_scale[:, None, None, None] * drift[None, :, :, :]
    component_p = jax_softmax(jnp, logits, axis=-1)
    mixed = jnp.einsum("tr,trpc->tpc", regime_probabilities, component_p)
    numpyro.sample("observed", dist.Categorical(probs=mixed), obs=y)
    next_regime = jnp.matmul(regime_probabilities[-1], transition)
    next_logits = jnp.einsum("rpfc,f->rpc", beta, X_next) + drift
    next_component = jax_softmax(jnp, next_logits, axis=-1)
    next_p = jnp.einsum("r,rpc->pc", next_regime, next_component)
    numpyro.deterministic("next_probabilities", next_p)


def _hdp_model(y: Any, classes: int, positions: int, sticky: bool) -> None:
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    components = 5
    alpha = numpyro.sample("alpha", dist.Gamma(2.0, 1.0))
    gamma = numpyro.sample("gamma", dist.Gamma(2.0, 1.0))
    v = numpyro.sample("global_stick", dist.Beta(jnp.ones(components - 1), gamma))
    beta = _stick_breaking(jnp, v)
    emissions = numpyro.sample(
        "emissions", dist.Dirichlet(jnp.ones(classes)).expand((components, positions))
    )
    if sticky:
        kappa = numpyro.sample("sticky_mass", dist.Gamma(4.0, 1.0))
        transition = numpyro.sample(
            "transition",
            dist.Dirichlet(alpha * beta[None, :] + kappa * jnp.eye(components)),
        )
        state_probability = beta
        weights = []
        for _ in range(y.shape[0]):
            weights.append(state_probability)
            state_probability = jnp.matmul(state_probability, transition)
        weights = jnp.stack(weights)
        p = jnp.einsum("tk,kpc->tpc", weights, emissions)
        numpyro.sample("observed", dist.Categorical(probs=p), obs=y)
        next_p = jnp.einsum("k,kpc->pc", state_probability, emissions)
    else:
        local_weights = numpyro.sample(
            "position_weights", dist.Dirichlet(alpha * beta).expand((positions,))
        )
        p_position = jnp.einsum("pk,kpc->pc", local_weights, emissions)
        numpyro.sample("observed", dist.Categorical(probs=p_position), obs=y)
        next_p = p_position
    numpyro.deterministic("next_probabilities", next_p)


def _dp_changepoint_model(y: Any, classes: int, positions: int) -> None:
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    segments = 5
    n = y.shape[0]
    gamma = numpyro.sample("gamma", dist.Gamma(2.0, 1.0))
    v = numpyro.sample("stick", dist.Beta(jnp.ones(segments - 1), gamma))
    weights = _stick_breaking(jnp, v)
    locations = numpyro.sample(
        "locations", dist.Beta(jnp.arange(1, segments + 1), jnp.arange(segments, 0, -1))
    )
    sharpness = numpyro.sample("sharpness", dist.LogNormal(2.0, 0.4))
    emissions = numpyro.sample(
        "emissions", dist.Dirichlet(jnp.ones(classes)).expand((segments, positions))
    )
    time = jnp.linspace(0.0, 1.0, n)
    gates = jnp.exp(-sharpness * jnp.abs(time[:, None] - locations[None, :])) * weights[None, :]
    gates = gates / jnp.sum(gates, axis=-1, keepdims=True)
    p = jnp.einsum("ts,spc->tpc", gates, emissions)
    numpyro.sample("observed", dist.Categorical(probs=p), obs=y)
    next_gate = jnp.exp(-sharpness * jnp.abs(1.0 - locations)) * weights
    next_gate = next_gate / next_gate.sum()
    numpyro.deterministic("next_probabilities", jnp.einsum("s,spc->pc", next_gate, emissions))


def build_numpyro_graph(
    spec: Any,
    *,
    y: np.ndarray,
    classes: int,
    target_mode: str,
    geometry: Any,
    config: Any,
    seed: int,
) -> NumPyroGraph:
    values = bounded_training_data(y, config.native_max_train_rows).astype(int)
    if values.ndim == 1:
        values = values[:, None]
    model_id = spec.model_id
    if model_id not in NUMPYRO_NATIVE_MODEL_IDS:
        raise KeyError(f"no numpyro primary graph for {model_id}")
    args: tuple[Any, ...]
    if model_id == "pp-hsmm-categorical":
        model = _hsmm_model
        args = (values, classes, values.shape[1])
    elif model_id in {"pp-switching-logistic-normal", "pp-switching-dynamic-regression"}:
        X, X_next = categorical_design(values, classes, degree=2, harmonics=1)
        model = _switching_logistic_model
        args = (
            values,
            classes,
            values.shape[1],
            X,
            X_next,
            model_id == "pp-switching-dynamic-regression",
        )
    elif model_id == "pp-hierarchical-dirichlet-process":
        model = _hdp_model
        args = (values, classes, values.shape[1], False)
    elif model_id == "pp-sticky-hdp-hmm":
        model = _hdp_model
        args = (values, classes, values.shape[1], True)
    elif model_id == "pp-dp-changepoint":
        model = _dp_changepoint_model
        args = (values, classes, values.shape[1])
    else:
        raise KeyError(f"no NumPyro graph for {model_id}")
    return NumPyroGraph(
        model=model,
        model_args=args,
        model_kwargs={},
        graph_id=spec.native_graph_id,
        metadata={
            "training_rows_used": len(values),
            "classes": classes,
            "positions": int(values.shape[1]),
            "seed": seed,
        },
    )
