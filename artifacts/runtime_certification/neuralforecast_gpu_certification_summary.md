# NeuralForecast GPU Runtime Certification

- Status: **PASS**
- GPU: `NVIDIA GeForce RTX 5070 Ti`
- PyTorch: `2.9.1+cu128`
- CUDA build: `12.8`
- Certified models: **23/23**
- Highest observed peak VRAM: **VanillaTransformer 112.13 MiB**

| Phase | Model | Status | Forward calls | Peak VRAM MiB | CUDA | Finite |
|---|---|---:|---:|---:|---:|---:|
| phase1 | DLinear | PASS | 5 | 16.60 | True | True |
| phase1 | NLinear | PASS | 5 | 16.59 | True | True |
| phase1 | MLP | PASS | 5 | 17.77 | True | True |
| phase1 | NHITS | PASS | 5 | 19.92 | True | True |
| phase1 | NBEATS | PASS | 5 | 18.05 | True | True |
| phase1 | PatchTST | PASS | 5 | 34.01 | True | True |
| phase2 | RNN | PASS | 5 | 27.52 | True | True |
| phase2 | GRU | PASS | 5 | 28.78 | True | True |
| phase2 | LSTM | PASS | 5 | 29.07 | True | True |
| phase2 | DilatedRNN | PASS | 5 | 30.18 | True | True |
| phase2 | TCN | PASS | 5 | 17.87 | True | True |
| phase2 | BiTCN | PASS | 5 | 38.54 | True | True |
| phase2 | TiDE | PASS | 5 | 18.37 | True | True |
| phase2 | TimesNet | PASS | 5 | 22.05 | True | True |
| phase2 | TFT | PASS | 5 | 85.86 | True | True |
| phase2 | VanillaTransformer | PASS | 5 | 112.13 | True | True |
| phase3 | Autoformer | PASS | 5 | 82.65 | True | True |
| phase3 | FEDformer | PASS | 5 | 48.31 | True | True |
| phase3 | Informer | PASS | 5 | 59.19 | True | True |
| phase3 | DeepAR | PASS | 5 | 56.26 | True | True |
| phase3 | DeepNPTS | PASS | 5 | 17.88 | True | True |
| phase3 | KAN | PASS | 5 | 22.69 | True | True |
| phase3 | NBEATSx | PASS | 5 | 18.05 | True | True |

## Certification criteria

- Model construction succeeded.
- Training reached the configured maximum steps.
- Prediction completed successfully.
- Forward execution occurred on CUDA.
- CUDA allocation increased during execution.
- Prediction output contained only finite values.

xLSTM is excluded from this main-environment report because it is isolated in a separate dependency environment.
