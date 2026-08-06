# Lightweight model lane selection

## Decision

`DLinear`, `TSMixer`, `LightTS`, `SegRNN`, `FreTS`, `SCINet`, `TimeFilter`, and `TiDE`
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
| TiDE | single PyTorch model | depth aliasing and time-feature geometry | certified |
| Koopa | model imports and constructs `data_provider` | dataset-bound constructor | deferred |
| PAttn | Transformer layers and `reformer_pytorch` import | dependency closure | blocked dependency |
| WPMixer | wavelet decomposition | coefficient and patch geometry | blocked dependency |

TiDE was selected ahead of Koopa because the pinned TiDE class can be constructed from
a closed single-file source. Koopa computes its frequency mask by opening the training
data provider during construction, so its executable closure includes data loading and
split materialization rather than only model geometry.

TiDE depths above one were not treated as ordinary independent stacks. The pinned source
uses list multiplication for repeated blocks, which aliases one module instance. The
certified lane fixes encoder and decoder depth to one and verifies the exact parameter
formula, six geometries, separate-process persistence, and checkpoint tamper rejection.
