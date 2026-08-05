# P8 Verification Report

Status: `PARTIALLY_VERIFIED / CERTIFICATION_HARNESS_IMPLEMENTED / REAL_RUNTIME_PENDING`.

## Executed locally

- runtime certification pure tests: `PASS`;
- torch forward-hook input/output device observation: `PASS` on CPU;
- fake Torch/GluonTS/Uni2TS provider boundary: `PASS`;
- strict external GPU CSV parsing: `PASS`;
- distinct-process and exact prediction-hash comparison: `PASS`;
- changed-quantile rejection: `PASS`;
- artifact and covariate identity comparison: `PASS`;
- CPU fallback and missing CUDA PID rejection: `PASS`;
- provider PID release validation: `PASS`;
- certification CLI and provider runner compileall: `PASS`;
- Python source lines over 100 characters: `0`.

## Not executed or certified

- isolated lockfile generation and frozen synchronization;
- real `uni2ts==2.0.0` import through either isolated lane;
- real pinned snapshot load and all-nine-quantile inference;
- two real provider processes using the target snapshot;
- actual external GPU PID, GPU UUID, VRAM, and post-exit release evidence;
- Ruff, mypy, full repository pytest, or successful GitHub Actions steps;
- OOF, Holdout, Prospective, accuracy, calibration, baseline superiority, or fine-tuning.

No fake, mocked, or source-inspection evidence is represented as real model-runtime certification.
