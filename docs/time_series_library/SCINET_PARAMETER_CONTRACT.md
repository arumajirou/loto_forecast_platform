# SCINet parameter and output contract

## Source

- pinned model: `models/SCINet.py`;
- Git blob: `740d0f7d88e8a94aa7fe12c745f0876af7b0fc08`;
- SHA-256: `06dcae9cfce5d3dc09e8db9b537479421848ee678ffbd1d3ca0b5c335a1baf25`.

## Accepted request fields

- `seq_len >= 8`;
- `pred_len >= 1`;
- `channels >= 1`;
- `scinet_stacks` is `1` or `2`;
- `dropout` must be `0.0`.

The upstream tree level is fixed at `3`. Sequence lengths below eight eventually
produce an empty branch in the recursive split and are rejected before construction.

The upstream `SCIBlock` constructor does not pass its dropout argument into the four
`CausalConvBlock` instances. Non-zero dropout would therefore be silently ignored, so
this provider rejects it.

## Output contract

The upstream `forward` result has length:

`raw_output_length = 2 * seq_len + pred_len`

Its first `seq_len` rows are a zero-filled prefix. The provider emits only the final
`pred_len` rows as the formal forecast and records both raw and formal shapes.

## Structural contract

For tree level three:

- tree depth: `4`;
- `SCIBlock` count per stack: `15`;
- `CausalConvBlock` count per stack: `60`;
- convolution kernel size: `5`.

The exact parameter count is checked before fit and reload.

For one stack:

`600 * channels^2 + 120 * channels + seq_len * (seq_len + pred_len)`

For two stacks:

`1200 * channels^2 + 240 * channels + seq_len * pred_len + (seq_len + pred_len)^2`

## Persistence contract

The checkpoint stores the effective configuration and derived tree geometry. Reload
recomputes them, rejects modified geometry, constructs the exact pinned class, performs
strict state loading, and validates the raw-prefix and final forecast shapes.
