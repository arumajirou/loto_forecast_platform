from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

PYRO_NATIVE_MODEL_IDS = frozenset(
    {
        "pp-bayesian-mlp",
        "pp-bayesian-tcn",
        "pp-bayesian-gru",
        "pp-bayesian-lstm",
        "pp-bayesian-transformer",
        "pp-variational-rnn",
        "pp-deep-markov-model",
        "pp-neural-hmm",
        "pp-bayesian-embedding-categorical",
        "pp-bayesian-neural-ordinal",
    }
)

from loto.probabilistic.models.native_common import bounded_training_data


@dataclass(frozen=True)
class PyroGraph:
    model: Callable[..., Any]
    model_args: tuple[Any, ...]
    model_kwargs: dict[str, Any]
    graph_id: str
    metadata: dict[str, Any]


def _sample_matrix(
    pyro: Any, dist: Any, name: str, rows: int, cols: int, scale: float = 0.35
) -> Any:
    return pyro.sample(
        name,
        dist.Normal(0.0, scale).expand((rows, cols)).to_event(2),
    )


def _sample_vector(pyro: Any, dist: Any, name: str, size: int, scale: float = 0.35) -> Any:
    return pyro.sample(name, dist.Normal(0.0, scale).expand((size,)).to_event(1))


def _base_inputs(torch: Any, y: Any, classes: int, positions: int) -> tuple[Any, Any]:
    import torch.nn.functional as F

    n = y.shape[0]
    previous = torch.cat([y[:1], y[:-1]], dim=0)
    one_hot = F.one_hot(previous, num_classes=classes).float()
    position = torch.eye(positions, device=y.device)[None, :, :].expand(n, -1, -1)
    time = torch.linspace(-1.0, 1.0, n, device=y.device)[:, None, None].expand(-1, positions, 1)
    x = torch.cat([one_hot, position, time], dim=-1)
    next_one_hot = F.one_hot(y[-1], num_classes=classes).float()
    next_position = torch.eye(positions, device=y.device)
    next_x = torch.cat(
        [next_one_hot, next_position, torch.full((positions, 1), 1.05, device=y.device)], dim=-1
    )
    return x, next_x


def _observe(pyro: Any, dist: Any, logits: Any, y: Any) -> None:
    pyro.sample(
        "observed",
        dist.Categorical(logits=logits.reshape(-1, logits.shape[-1])),
        obs=y.reshape(-1),
    )


def _mlp_model(y: Any, classes: int, positions: int, architecture: str) -> None:
    import pyro
    import pyro.distributions as dist
    import torch
    import torch.nn.functional as F

    x, next_x = _base_inputs(torch, y, classes, positions)
    input_dim = x.shape[-1]
    hidden = 12
    w1 = _sample_matrix(pyro, dist, "w1", input_dim, hidden)
    b1 = _sample_vector(pyro, dist, "b1", hidden)
    w2 = _sample_matrix(pyro, dist, "w2", hidden, classes)
    b2 = _sample_vector(pyro, dist, "b2", classes)
    hidden_values = torch.tanh(torch.matmul(x, w1) + b1)
    if architecture == "embedding":
        hidden_values = F.gelu(hidden_values)
    logits = torch.matmul(hidden_values, w2) + b2
    _observe(pyro, dist, logits, y)
    next_logits = torch.matmul(torch.tanh(torch.matmul(next_x, w1) + b1), w2) + b2
    pyro.deterministic("next_probabilities", torch.softmax(next_logits, dim=-1))


def _tcn_model(y: Any, classes: int, positions: int) -> None:
    import pyro
    import pyro.distributions as dist
    import torch
    import torch.nn.functional as F

    x, _ = _base_inputs(torch, y, classes, positions)
    n = y.shape[0]
    channels = 8
    # One sequence per position: (positions, input_channels, time)
    sequence = x.permute(1, 2, 0)
    kernel1 = pyro.sample(
        "kernel1", dist.Normal(0.0, 0.25).expand((channels, x.shape[-1], 3)).to_event(3)
    )
    bias1 = _sample_vector(pyro, dist, "bias1", channels)
    kernel2 = pyro.sample(
        "kernel2", dist.Normal(0.0, 0.25).expand((channels, channels, 3)).to_event(3)
    )
    bias2 = _sample_vector(pyro, dist, "bias2", channels)
    projection = _sample_matrix(pyro, dist, "projection", channels, classes)
    projection_bias = _sample_vector(pyro, dist, "projection_bias", classes)
    h1 = torch.tanh(F.conv1d(F.pad(sequence, (2, 0)), kernel1, bias=bias1))
    h2 = torch.tanh(F.conv1d(F.pad(h1, (4, 0)), kernel2, bias=bias2, dilation=2))
    logits = torch.einsum("pct,ck->tpk", h2, projection) + projection_bias
    _observe(pyro, dist, logits, y)
    next_logits = torch.matmul(h2[:, :, -1].T, projection) + projection_bias
    pyro.deterministic("next_probabilities", torch.softmax(next_logits, dim=-1))


def _gru_model(y: Any, classes: int, positions: int, *, lstm: bool = False) -> None:
    import pyro
    import pyro.distributions as dist
    import torch

    x, next_x = _base_inputs(torch, y, classes, positions)
    hidden = 10
    input_dim = x.shape[-1]
    gate_count = 4 if lstm else 3
    w_x = _sample_matrix(pyro, dist, "w_x", input_dim, gate_count * hidden)
    w_h = _sample_matrix(pyro, dist, "w_h", hidden, gate_count * hidden)
    bias = _sample_vector(pyro, dist, "bias", gate_count * hidden)
    projection = _sample_matrix(pyro, dist, "projection", hidden, classes)
    projection_bias = _sample_vector(pyro, dist, "projection_bias", classes)
    h = torch.zeros((positions, hidden), device=y.device)
    c = torch.zeros_like(h)
    outputs = []
    for t in range(y.shape[0]):
        input_gates = torch.matmul(x[t], w_x) + bias
        recurrent_gates = torch.matmul(h, w_h)
        if lstm:
            i_x, f_x, g_x, o_x = input_gates.chunk(4, dim=-1)
            i_h, f_h, g_h, o_h = recurrent_gates.chunk(4, dim=-1)
            i = torch.sigmoid(i_x + i_h)
            f = torch.sigmoid(f_x + f_h)
            g = torch.tanh(g_x + g_h)
            o = torch.sigmoid(o_x + o_h)
            c = f * c + i * g
            h = o * torch.tanh(c)
        else:
            r_x, z_x, n_x = input_gates.chunk(3, dim=-1)
            r_h, z_h, n_h = recurrent_gates.chunk(3, dim=-1)
            r = torch.sigmoid(r_x + r_h)
            z = torch.sigmoid(z_x + z_h)
            candidate = torch.tanh(n_x + r * n_h)
            h = (1.0 - z) * candidate + z * h
        outputs.append(torch.matmul(h, projection) + projection_bias)
    logits = torch.stack(outputs)
    _observe(pyro, dist, logits, y)
    input_gates = torch.matmul(next_x, w_x) + bias
    recurrent_gates = torch.matmul(h, w_h)
    if lstm:
        i_x, f_x, g_x, o_x = input_gates.chunk(4, dim=-1)
        i_h, f_h, g_h, o_h = recurrent_gates.chunk(4, dim=-1)
        i = torch.sigmoid(i_x + i_h)
        f = torch.sigmoid(f_x + f_h)
        g = torch.tanh(g_x + g_h)
        o = torch.sigmoid(o_x + o_h)
        c = f * c + i * g
        h = o * torch.tanh(c)
    else:
        r_x, z_x, n_x = input_gates.chunk(3, dim=-1)
        r_h, z_h, n_h = recurrent_gates.chunk(3, dim=-1)
        r = torch.sigmoid(r_x + r_h)
        z = torch.sigmoid(z_x + z_h)
        candidate = torch.tanh(n_x + r * n_h)
        h = (1.0 - z) * candidate + z * h
    next_logits = torch.matmul(h, projection) + projection_bias
    pyro.deterministic("next_probabilities", torch.softmax(next_logits, dim=-1))


def _transformer_model(y: Any, classes: int, positions: int) -> None:
    import pyro
    import pyro.distributions as dist
    import torch

    x, next_x = _base_inputs(torch, y, classes, positions)
    width = 12
    w_in = _sample_matrix(pyro, dist, "w_in", x.shape[-1], width)
    b_in = _sample_vector(pyro, dist, "b_in", width)
    wq = _sample_matrix(pyro, dist, "wq", width, width)
    wk = _sample_matrix(pyro, dist, "wk", width, width)
    wv = _sample_matrix(pyro, dist, "wv", width, width)
    wo = _sample_matrix(pyro, dist, "wo", width, width)
    ff1 = _sample_matrix(pyro, dist, "ff1", width, 2 * width)
    ff2 = _sample_matrix(pyro, dist, "ff2", 2 * width, width)
    projection = _sample_matrix(pyro, dist, "projection", width, classes)
    h = torch.tanh(torch.matmul(x, w_in) + b_in).permute(1, 0, 2)
    q, k, v = torch.matmul(h, wq), torch.matmul(h, wk), torch.matmul(h, wv)
    scores = torch.matmul(q, k.transpose(-1, -2)) / np.sqrt(width)
    mask = torch.triu(torch.ones_like(scores), diagonal=1).bool()
    attention = torch.softmax(scores.masked_fill(mask, -1e9), dim=-1)
    context = torch.matmul(attention, v)
    h = h + torch.matmul(context, wo)
    h = h + torch.matmul(torch.tanh(torch.matmul(h, ff1)), ff2)
    logits = torch.matmul(h, projection).permute(1, 0, 2)
    _observe(pyro, dist, logits, y)
    # Forecast token attends to all historical tokens for its position.
    q_next = torch.matmul(torch.tanh(torch.matmul(next_x, w_in) + b_in), wq)
    score_next = torch.einsum("pd,pnd->pn", q_next, k) / np.sqrt(width)
    context_next = torch.einsum("pn,pnd->pd", torch.softmax(score_next, -1), v)
    next_h = torch.tanh(torch.matmul(next_x, w_in) + b_in) + torch.matmul(context_next, wo)
    next_h = next_h + torch.matmul(torch.tanh(torch.matmul(next_h, ff1)), ff2)
    pyro.deterministic("next_probabilities", torch.softmax(torch.matmul(next_h, projection), -1))


def _latent_sequence_model(y: Any, classes: int, positions: int, model_id: str) -> None:
    import pyro
    import pyro.distributions as dist
    import torch

    latent = 8
    transition = _sample_matrix(pyro, dist, "transition", latent, latent, 0.25)
    emission = _sample_matrix(pyro, dist, "emission", latent, positions * classes, 0.3)
    bias = _sample_vector(pyro, dist, "emission_bias", positions * classes)
    z = pyro.sample("z_0", dist.Normal(torch.zeros(latent, device=y.device), 1.0).to_event(1))
    logits = []
    for t in range(y.shape[0]):
        if t:
            mean = torch.tanh(torch.matmul(z, transition))
            scale = 0.35 if model_id == "pp-variational-rnn" else 0.5
            z = pyro.sample(f"z_{t}", dist.Normal(mean, scale).to_event(1))
        current = torch.matmul(z, emission) + bias
        logits.append(current.reshape(positions, classes))
    logits_tensor = torch.stack(logits)
    _observe(pyro, dist, logits_tensor, y)
    next_mean = torch.tanh(torch.matmul(z, transition))
    next_z = pyro.sample("z_next", dist.Normal(next_mean, 0.35).to_event(1))
    next_logits = (torch.matmul(next_z, emission) + bias).reshape(positions, classes)
    pyro.deterministic("next_probabilities", torch.softmax(next_logits, dim=-1))


def _neural_hmm_model(y: Any, classes: int, positions: int) -> None:
    import pyro
    import pyro.distributions as dist
    import torch

    regimes = 4
    transition_logits = pyro.sample(
        "transition_logits", dist.Normal(0.0, 0.6).expand((regimes, regimes)).to_event(2)
    )
    emission_logits = pyro.sample(
        "emission_logits",
        dist.Normal(0.0, 0.8).expand((regimes, positions, classes)).to_event(3),
    )
    state = pyro.sample(
        "state_0",
        dist.RelaxedOneHotCategoricalStraightThrough(
            temperature=torch.tensor(0.5, device=y.device),
            logits=torch.zeros(regimes, device=y.device),
        ),
    )
    logits_rows = []
    transition = torch.softmax(transition_logits, -1)
    for t in range(y.shape[0]):
        logits_rows.append(torch.einsum("r,rpc->pc", state, emission_logits))
        next_probs = torch.matmul(state, transition)
        state = pyro.sample(
            f"state_{t + 1}",
            dist.RelaxedOneHotCategoricalStraightThrough(
                temperature=torch.tensor(0.5, device=y.device), probs=next_probs
            ),
        )
    _observe(pyro, dist, torch.stack(logits_rows), y)
    next_logits = torch.einsum("r,rpc->pc", state, emission_logits)
    pyro.deterministic("next_probabilities", torch.softmax(next_logits, -1))


def _embedding_model(y: Any, classes: int, positions: int) -> None:
    import pyro
    import pyro.distributions as dist
    import torch

    embedding_dim = 8
    value_embedding = pyro.sample(
        "value_embedding", dist.Normal(0.0, 0.5).expand((classes, embedding_dim)).to_event(2)
    )
    position_embedding = pyro.sample(
        "position_embedding", dist.Normal(0.0, 0.5).expand((positions, embedding_dim)).to_event(2)
    )
    projection = _sample_matrix(pyro, dist, "projection", 2 * embedding_dim, classes)
    bias = _sample_vector(pyro, dist, "bias", classes)
    previous = torch.cat([y[:1], y[:-1]], dim=0)
    pos = torch.arange(positions, device=y.device)
    hidden = torch.cat(
        [value_embedding[previous], position_embedding[pos][None, :, :].expand(y.shape[0], -1, -1)],
        dim=-1,
    )
    logits = torch.matmul(torch.tanh(hidden), projection) + bias
    _observe(pyro, dist, logits, y)
    next_hidden = torch.cat([value_embedding[y[-1]], position_embedding], dim=-1)
    pyro.deterministic(
        "next_probabilities",
        torch.softmax(torch.matmul(torch.tanh(next_hidden), projection) + bias, -1),
    )


def _ordinal_neural_model(y: Any, classes: int, positions: int) -> None:
    import pyro
    import pyro.distributions as dist
    import torch

    x, next_x = _base_inputs(torch, y, classes, positions)
    hidden = 10
    w1 = _sample_matrix(pyro, dist, "w1", x.shape[-1], hidden)
    b1 = _sample_vector(pyro, dist, "b1", hidden)
    w_location = _sample_matrix(pyro, dist, "w_location", hidden, 1)
    raw_gaps = pyro.sample(
        "cutpoint_gaps", dist.LogNormal(-0.2, 0.5).expand((positions, classes - 1)).to_event(2)
    )
    cutpoints = torch.cumsum(raw_gaps, -1)
    cutpoints = cutpoints - cutpoints.mean(-1, keepdim=True)
    location = torch.matmul(torch.tanh(torch.matmul(x, w1) + b1), w_location).squeeze(-1)
    lower = torch.sigmoid(cutpoints[None, :, :] - location[:, :, None])
    probabilities = torch.cat(
        [lower[:, :, :1], lower[:, :, 1:] - lower[:, :, :-1], 1.0 - lower[:, :, -1:]],
        dim=-1,
    )
    pyro.sample("observed", dist.Categorical(probs=probabilities), obs=y)
    next_location = torch.matmul(torch.tanh(torch.matmul(next_x, w1) + b1), w_location).squeeze(-1)
    next_lower = torch.sigmoid(cutpoints - next_location[:, None])
    next_p = torch.cat(
        [next_lower[:, :1], next_lower[:, 1:] - next_lower[:, :-1], 1.0 - next_lower[:, -1:]],
        dim=-1,
    )
    pyro.deterministic("next_probabilities", next_p)


def build_pyro_graph(
    spec: Any,
    *,
    y: np.ndarray,
    classes: int,
    target_mode: str,
    geometry: Any,
    config: Any,
    seed: int,
    device: str,
) -> PyroGraph:
    import torch

    values = bounded_training_data(y, config.native_max_train_rows).astype(np.int64)
    if values.ndim == 1:
        values = values[:, None]
    tensor = torch.as_tensor(values, dtype=torch.long, device=device)
    model_id = spec.model_id
    if model_id not in PYRO_NATIVE_MODEL_IDS:
        raise KeyError(f"no pyro primary graph for {model_id}")
    if model_id == "pp-bayesian-mlp":
        model, args = _mlp_model, (tensor, classes, values.shape[1], "mlp")
    elif model_id == "pp-bayesian-tcn":
        model, args = _tcn_model, (tensor, classes, values.shape[1])
    elif model_id == "pp-bayesian-gru":
        model, args = _gru_model, (tensor, classes, values.shape[1], False)
    elif model_id == "pp-bayesian-lstm":
        model, args = _gru_model, (tensor, classes, values.shape[1], True)
    elif model_id == "pp-bayesian-transformer":
        model, args = _transformer_model, (tensor, classes, values.shape[1])
    elif model_id in {"pp-variational-rnn", "pp-deep-markov-model"}:
        model, args = _latent_sequence_model, (tensor, classes, values.shape[1], model_id)
    elif model_id == "pp-neural-hmm":
        model, args = _neural_hmm_model, (tensor, classes, values.shape[1])
    elif model_id == "pp-bayesian-embedding-categorical":
        model, args = _embedding_model, (tensor, classes, values.shape[1])
    elif model_id == "pp-bayesian-neural-ordinal":
        model, args = _ordinal_neural_model, (tensor, classes, values.shape[1])
    else:
        raise KeyError(f"no Pyro graph for {model_id}")
    return PyroGraph(
        model=model,
        model_args=args,
        model_kwargs={},
        graph_id=spec.native_graph_id,
        metadata={
            "training_rows_used": len(values),
            "classes": classes,
            "positions": int(values.shape[1]),
            "seed": seed,
            "device": device,
        },
    )
