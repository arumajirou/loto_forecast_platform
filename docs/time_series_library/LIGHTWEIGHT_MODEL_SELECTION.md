# Lightweight model lane selection

## Decision

`DLinear`, `TSMixer`, `LightTS`, `SegRNN`, `FreTS`, and `SCINet` are CPU
runtime-certified in the pinned-source provider.

## Candidate comparison

| Model | Pinned Git blob | Direct dependencies | Contract constraints | Decision |
|---|---|---|---|---|
| DLinear | `3f4d666a9ffe7fb6f58627ba43f1a9d3d9804d78` | PyTorch and Autoformer decomposition | odd moving-average kernel | certified |
| TSMixer | `76884d467f17d64aa87d8e22cc9f0aa6231914cf` | PyTorch only | `e_layers >= 1`, bounded `dropout` | certified |
| LightTS | `a2051e44d864ec4ec5e72e59660b98c30c93a902` | PyTorch only | explicit chunk size, padding opt-in, width reductions | certified |
| SegRNN | `afff1bc07dd14d227bbecdd36941d57f8aa8f63e` | PyTorch and pinned Autoformer import | segment divisibility and even `d_model` | certified |
| FreTS | `ca4e0b648db42a1846b7a0a9a661a39177f47005` | PyTorch and NumPy | channel mode, FFT geometry, parameter formula | certified |
| SCINet | `740d0f7d88e8a94aa7fe12c745f0876af7b0fc08` | PyTorch only | minimum sequence, stacks, raw-output slicing | certified |
| PAttn | `b6f4634aab87bff704a8bdc250f9790eba2cb820` | Transformer layers, einops, reformer-pytorch import | dependency closure and patch geometry | blocked dependency |
| WPMixer | `9271b2b3d8283a5625236bc8aebd766e89e7fd82` | wavelet decomposition | coefficient and patch geometry | blocked dependency |
| TimeFilter | `ff952b4a7741ad2772fde3e41b0d97bc2bbe7e19` | three pinned layer files | graph masks and patch geometry | deferred |

SCINet was selected as the sixth lane because its executable source is a single
PyTorch file. Certification explicitly covers the fixed recursive tree, stack modes,
ignored-dropout boundary, raw zero prefix, final forecast slicing, parameter formulas,
separate-process persistence, and checkpoint tamper rejection.
