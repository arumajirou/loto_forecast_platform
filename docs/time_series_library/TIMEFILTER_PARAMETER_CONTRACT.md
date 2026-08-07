# TimeFilter parameter and graph contract

## Pinned source closure

- `models/TimeFilter.py`: `ff952b4a7741ad2772fde3e41b0d97bc2bbe7e19`;
- `layers/TimeFilter_layers.py`: `437c3bfd135c2d2b907c7332311ac553c8a2d523`;
- `layers/StandardNorm.py`: `990d0fdc17751b724354e70b89fd6d3ff0f4dd29`;
- `layers/Embed.py`: `977e25568d37b9dd0efd442dcc5b33eab9843d71`.

All four files are verified before import, fit, and reload. Altering only `Embed.py`
was rejected before construction.

## Accepted geometry

- `patch_len >= 1` and `patch_len <= seq_len`;
- `seq_len % patch_len == 0`;
- `d_model` is even because pinned positional embedding requires paired sine/cosine widths;
- `d_model % n_heads == 0`;
- `d_ff >= 1`, `e_layers >= 1`;
- `alpha` and `top_p` are in `[0, 1]`;
- `token_count = channels * (seq_len / patch_len) <= 10000`.

The divisibility rule prevents the pinned model from producing a flattened patch count
that cannot be reshaped into `[batch, channels, num_patches, d_model]`.

## Graph-mask contract

For `N = seq_len / patch_len`, `C = channels`, and `L = C * N`:

- mask shape: `[L, 3, L]`;
- same-time region size per row: `C - 1`;
- same-channel region size per row: `N - 1`;
- cross region size per row: `(C - 1) * (N - 1)`;
- self edges are excluded;
- KNN zero count: `int(alpha * L)`;
- `top_p = 0` uses the identity-only gating path;
- `top_p > 0` enables noisy gating during training and deterministic gating in eval mode.

## Exact parameter formula

Let `D=d_model`, `H=n_heads`, `F=d_ff`, `E=e_layers`, `P=patch_len`,
`N=seq_len/P`, `L=channels*N`, and `Dh=D/H`.

- patch projection: `P*D + D`;
- each graph block: `2*Dh^2 + 2*Dh + 6*L + D^2 + 6*D + 2*D*F + F`;
- forecast head: `pred_len*D*N + pred_len`.

Total parameters are the patch projection plus `E` graph blocks plus the forecast head.
The formula is checked before fit and reload.

## Persistence

The checkpoint stores the complete effective configuration and derived graph geometry.
Reload recomputes all fields, rejects modified geometry, constructs the exact pinned
class, performs strict state loading, and validates finite CPU output shape.
