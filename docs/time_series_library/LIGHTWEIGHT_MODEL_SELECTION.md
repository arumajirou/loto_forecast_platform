# Lightweight model lane selection

## Decision

`DLinear`, `TSMixer`, `LightTS`, `SegRNN`, and `FreTS` are CPU runtime-certified in
the pinned-source provider.

## Candidate comparison

| Model | Pinned Git blob | Direct dependencies | Contract constraints | Decision |
|---|---|---|---|---|
| DLinear | `3f4d666a9ffe7fb6f58627ba43f1a9d3d9804d78` | PyTorch and Autoformer decomposition | odd moving-average kernel | certified |
| TSMixer | `76884d467f17d64aa87d8e22cc9f0aa6231914cf` | PyTorch only | `e_layers >= 1`, bounded `dropout` | certified |
| LightTS | `a2051e44d864ec4ec5e72e59660b98c30c93a902` | PyTorch only | explicit chunk size, padding opt-in, width reductions | certified |
| SegRNN | `afff1bc07dd14d227bbecdd36941d57f8aa8f63e` | PyTorch and pinned Autoformer import | segment divisibility and even `d_model` | certified |
| FreTS | `ca4e0b648db42a1846b7a0a9a661a39177f47005` | PyTorch and NumPy | channel-mode literal, FFT geometry, parameter formula | certified |
| PAttn | `b6f4634aab87bff704a8bdc250f9790eba2cb820` | PyTorch, einops, transformer layers | patch/stride geometry and attention dependencies | deferred |
| WPMixer | `9271b2b3d8283a5625236bc8aebd766e89e7fd82` | PyTorch and wavelet decomposition | wavelet levels, coefficient lengths, patch geometry | deferred |

FreTS was selected as the fifth lane because its source is self-contained apart from
PyTorch and NumPy. Both channel-frequency modes, the fixed 128/256 architecture, FFT
bin counts, parameter formula, separate-process persistence, and checkpoint tamper
rejection are now represented explicitly.
