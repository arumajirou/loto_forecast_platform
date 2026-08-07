# Toto 2.0 4M isolated runtime executor

Status: `IMPLEMENTED / DEPENDENCY_LIGHT_VERIFIED / REAL_RUNTIME_PENDING`.

## Purpose

The executor runs only in the Python 3.12 Toto lane. It does not register Toto in the shared
provider registry and does not import Toto packages from the root environment.

## Fail-closed boundaries

Before model loading, the executor requires:

- the snapshot directory name to equal the pinned model revision;
- exact SHA-256 matches for `README.md`, `config.json`, and `model.safetensors`;
- the pinned model weight size;
- Python 3.12, `toto-2==2.0.0`, `toto-models==1.0.0`, and Torch 2.13.0;
- CUDA 13.0 when CUDA execution is requested;
- formal context lengths 128, 256, or 512;
- decode block sizes divisible by the native patch size 32.

The model must load as `Toto2Model`, expose patch size 32 and quantile knots q0.1 through q0.9,
and contain exactly 4,144,448 parameters.

## Runtime evidence

The child process writes the native tensor and internal runtime facts. The parent certification
process holds the child after GPU model loading, captures the exact child PID through
`nvidia-smi`, then releases inference. Two distinct child processes are run and their `.npy`
outputs must be exactly equal.

Contract tests do not constitute new model inference. Real runtime certification remains pending
until the target host generates and reviews an isolated lock and executes the runbook.
