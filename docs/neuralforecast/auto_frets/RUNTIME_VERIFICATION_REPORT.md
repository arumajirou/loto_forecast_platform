# AutoFreTS Runtime Verification Report

## Publication status

```text
PARTIALLY_VERIFIED
ADAPTER_AND_SOURCE_TESTS_PASS
REAL_RUNTIME_PENDING
NOT_REGISTERED
ACCURACY_NOT_EVALUATED
```

## Verified during authoring

- strict Pydantic request and response contracts;
- CPU/GPU policy gates;
- fixed float32 precision gate;
- FreTS-specific FFT and parameter evidence gates;
- deterministic 10-file source inventory;
- canonical source-tree digest;
- clean Git, branch, and symlink rejection logic;
- source snapshot roundtrip;
- common SDK identity mapping;
- shell-free worker command construction;
- CPU CUDA-hiding environment;
- provider response mapping;
- PID-scoped GPU parser;
- deterministic synthetic input;
- nested FreTS model evidence extraction;
- structured failure-sealing path;
- documentation manifest and SHA-256 inventory.

## Authoring checks

The final publication files must pass:

```text
focused pytest
compileall
Python AST parse
JSON parse
shell syntax
100-character Python line policy
secret-pattern scan
cache cleanup
RUNTIME_ARTIFACT_MANIFEST verification
RUNTIME_SHA256SUMS verification
local / GitHub blob identity
```

## Not executed

```text
real neuralforecast==3.2.0 import
real direct fit/predict/save/load
real Ray actor and trial
real Optuna study
CPU target-host lifecycle
GPU target-host lifecycle
GPU PID/UUID/VRAM/release
Ruff
mypy
full repository pytest
```

## Data boundary

No project dataset or actual value was opened. No Train, Validation, OOF,
Holdout, Prospective, prediction-lock, registry, promotion, or production
artifact was changed.

No Hit@±1, MAE, MSE, RMSE, position-level result, seed aggregate, baseline
superiority, or production eligibility is claimed.
