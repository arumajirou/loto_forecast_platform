# Lightweight model lane selection

## Decision

`DLinear`, `TSMixer`, `LightTS`, `SegRNN`, `FreTS`, `SCINet`, `TimeFilter`, `TiDE`,
and `FiLM` are CPU runtime-certified in the pinned-source provider.

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
| TiDE | single PyTorch model | depth aliasing and zero time features | certified |
| FiLM | single model plus SciPy | HiPPO buffers, spectral modes, global device | certified |
| Koopa | model plus training data provider | constructor opens Train loader | deferred |
| MICN | model plus Embed and Autoformer layers | multi-kernel convolution geometry | pending |
| TimesNet | model plus Embed and Conv_Blocks | FFT top-k and 2D padding geometry | pending |
| PAttn | Transformer layers and `reformer_pytorch` | dependency closure | blocked dependency |
| WPMixer | wavelet decomposition | coefficient and patch geometry | blocked dependency |

FiLM was selected ahead of MICN and TimesNet because its executable source is one
file and its SciPy dependency is available in the authoring environment. Its global
device selection is treated as a strict CPU-only boundary rather than hidden fallback.
