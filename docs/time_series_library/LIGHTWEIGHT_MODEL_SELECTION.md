# Lightweight model lane selection

## Decision

`DLinear`, `TSMixer`, `LightTS`, `SegRNN`, `FreTS`, `SCINet`, and `TimeFilter`
are CPU runtime-certified in the pinned-source provider.

## Candidate comparison

| Model | Direct dependency surface | Key contract | Decision |
|---|---|---|---|
| DLinear | model plus Autoformer decomposition | moving-average geometry | certified |
| TSMixer | single PyTorch model | layer and dropout bounds | certified |
| LightTS | single PyTorch model | chunk and explicit padding geometry | certified |
| SegRNN | model plus Autoformer import | segment divisibility | certified |
| FreTS | single model, PyTorch and NumPy | FFT mode and parameter formula | certified |
| SCINet | single PyTorch model | recursive tree and raw-output slicing | certified |
| TimeFilter | model plus three pinned layers | patches, graph masks, noisy gating | certified |
| PAttn | Transformer layers and `reformer_pytorch` import | dependency closure | blocked dependency |
| WPMixer | wavelet decomposition | coefficient and patch geometry | blocked dependency |

TimeFilter was certified only after its four-file executable closure, patch divisibility,
positional width, multi-head split, graph-mask region counts, KNN selection, noisy-gating
mode, exact parameter formula, separate-process persistence, and dependency tamper
rejection were represented explicitly.
