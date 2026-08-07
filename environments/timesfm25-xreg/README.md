# TimesFM 2.5 XReg environment

Status: `DEFERRED`.

The XReg runtime is intentionally isolated from the PyTorch runtime because its dependency stack includes JAX/CUDA and scikit-learn. No executable environment or training path is claimed in the first provider-contract PR.
