# FiLM parameter and runtime contract

## Pinned source

- `models/FiLM.py`: `1240e37047f26b0fd905151f0b2671255b6ec045`;
- SHA-256: `866054afc57411ebaf47c270566c05302b19acf3a3663b0b86e9153e386d2dc6`.

The source file is verified before import, construction, fit, and reload.

## Certified geometry

The CPU lane supports only long-term forecasting with:

- `pred_len >= 2`;
- `seq_len >= 4 * pred_len`;
- `channels >= 1`;
- `e_layers = 1`;
- `dropout = 0.0`;
- fixed HiPPO order `256`;
- fixed scales `[1, 2, 4]`;
- one fixed window size `[256]`;
- a CPU-only interpreter where `torch.cuda.is_available()` is false.

The history-length requirement ensures that each scale receives exactly
`pred_len`, `2 * pred_len`, and `4 * pred_len` input rows rather than a silently
truncated slice.

`pred_len=1` is rejected because the pinned spectral convolution then computes
zero Fourier modes and carries no spectral learning parameters.

## SciPy and device boundary

The pinned source uses SciPy to discretize the HiPPO state-space matrices and to
evaluate Legendre polynomials. The isolated declaration adds `scipy==1.17.0`.

The source chooses a module-global device at import time. A CUDA-visible process
would bind HiPPO buffers to CUDA even when the provider request says CPU. The
certified lane therefore rejects CUDA-visible interpreters before importing the
model. This is an explicit CPU-only lane, not CPU fallback.

## Spectral modes

Let `H = pred_len`. Under the certified `seq_len >= 4H` rule:

```text
modes = min(32, floor(H / 2))
```

Each of the three scales owns real and imaginary spectral tensors with shape:

```text
[256, 256, modes]
```

## Exact parameter formula

Let `C = channels` and `M = modes`.

- three spectral modules: `3 * 2 * 256 * 256 * M`;
- affine weight and bias: `2 * C`;
- scale mixer `Linear(3, 1)`: `3 + 1`.

Therefore:

```text
parameters = 393216 * M + 2 * C + 4
```

HiPPO matrices are registered buffers, not trainable parameters.

## Buffer geometry

Each of three scales stores:

- `A`: `[256, 256]`;
- `B`: `[256]`;
- `eval_matrix`: `[scale * pred_len, 256]`.

The total buffer element count is:

```text
3 * (256 * 256 + 256) + (1 + 2 + 4) * pred_len * 256
= 197376 + 1792 * pred_len
```

All parameter and buffer devices must be exactly `cpu`.

## Persistence

The checkpoint stores the complete effective configuration, derived geometry,
state dictionary, and model name. Reload recomputes geometry, rejects any modified
geometry, reconstructs the exact pinned class, uses strict state loading, and
requires finite output shape `[2, pred_len, channels]`.
