# TimesFM 2.5 Requirements

1. Keep the algorithm identity shared across PyTorch and Transformers checkpoints.
2. Reject unknown request fields and unpinned revisions.
3. Support arbitrary GameGeometry and series counts.
4. Preserve every requested horizon, native median, native mean, and q0.1 through q0.9.
5. Reject non-finite values, quantile crossing, and point/q0.5 disagreement.
6. Distinguish batched univariate inference from joint multivariate modeling.
7. Record measured device, process, and VRAM evidence; CUDA fallback is a failure.
8. Keep Holdout, Prospective, XReg training, LoRA training, shared worker/catalog, and CI changes out of this PR.
