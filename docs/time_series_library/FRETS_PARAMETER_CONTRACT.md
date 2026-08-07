# FreTS parameter contract

## Source identity

- upstream revision: `4e938a1767106324dd753b2a44832bf870a0252e`;
- `models/FreTS.py`: `ca4e0b648db42a1846b7a0a9a661a39177f47005`.

## Request parameters

- `seq_len >= 4`;
- `pred_len >= 1`;
- `channels >= 1`;
- `frets_channel_independence` is the literal string `"0"` or `"1"`.

The upstream implementation treats `"0"` as channel-frequency mixing enabled.
`"1"` skips the channel-frequency block while retaining the same registered
parameter tensors. The provider persists this effective mode in the checkpoint.

## Fixed upstream architecture

- embedding width: `128`;
- hidden width: `256`;
- sparsity threshold: `0.01`;
- initialization scale: `0.02`;
- temporal FFT bins: `seq_len // 2 + 1`;
- channel FFT bins: `channels // 2 + 1`.

The exact parameter-count contract is:

```text
66,432 + 32,768 * seq_len + 257 * pred_len
```

The parameter count is independent of channel count because the frequency-domain
weights and forecast head are shared across channels. Runtime construction fails if
the observed count differs from this formula.

## Persistence and reload

The checkpoint stores the effective config and derived frequency geometry. Reload
recomputes the geometry, compares it with the stored record, constructs the exact
model, performs strict state-dictionary loading, validates the input shape, and writes
a separately hashed prediction. Modified checkpoint geometry is rejected before
inference.

## Certification boundary

The certified runtime is Python 3.13.5 with Torch 2.10.0+cpu. Exact Torch 2.9.1, GPU,
real lottery metrics, Holdout, and Prospective execution remain pending.
