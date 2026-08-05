# Lightweight model lane selection

## Decision

`TSMixer` is the second CPU runtime-certified TSLib model after DLinear.

## Candidate comparison

| Model | Pinned Git blob | Direct dependencies | Contract constraints | Decision |
|---|---|---|---|---|
| TSMixer | `76884d467f17d64aa87d8e22cc9f0aa6231914cf` | PyTorch only | `e_layers >= 1`, positive `d_model`, bounded `dropout` | certified now |
| LightTS | `a2051e44d864ec4ec5e72e59660b98c30c93a902` | PyTorch only | chunk padding and nested `d_model // 4` reductions | next lane |
| SegRNN | `afff1bc07dd14d227bbecdd36941d57f8aa8f63e` | PyTorch and Autoformer layer | sequence and horizon divisibility by `seg_len` | next lane |

TSMixer was selected first because it has no optional imports and no external layer
module. LightTS and SegRNN remain pending until their shape constraints are represented
explicitly in the request contract and tested fail-closed.
