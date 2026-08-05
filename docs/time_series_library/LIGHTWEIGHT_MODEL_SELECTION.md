# Lightweight model lane selection

## Decision

`DLinear`, `TSMixer`, and `LightTS` are CPU runtime-certified in the pinned-source
provider. `SegRNN` is the next lightweight candidate.

## Candidate comparison

| Model | Pinned Git blob | Direct dependencies | Contract constraints | Decision |
|---|---|---|---|---|
| DLinear | `3f4d666a9ffe7fb6f58627ba43f1a9d3d9804d78` | PyTorch and Autoformer decomposition | odd moving-average kernel | certified |
| TSMixer | `76884d467f17d64aa87d8e22cc9f0aa6231914cf` | PyTorch only | `e_layers >= 1`, bounded `dropout` | certified |
| LightTS | `a2051e44d864ec4ec5e72e59660b98c30c93a902` | PyTorch only | explicit chunk size, padding opt-in, `d_model >= 16`, divisible by 4 | certified |
| SegRNN | `afff1bc07dd14d227bbecdd36941d57f8aa8f63e` | PyTorch and Autoformer layer import | sequence and horizon divisibility by `seg_len` | next lane |

LightTS was certified after its hidden padding behavior and nested integer-width
reductions were represented explicitly and tested fail-closed. SegRNN remains pending
until `seg_len`, source dependency, and horizon geometry are formalized.
