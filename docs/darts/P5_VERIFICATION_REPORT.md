# P5 local statistical verification

`PARTIALLY_VERIFIED / LOCAL_MATRIX_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

Executed locally:

- nine required campaign identities retained;
- missing runtime classes retained as dependency failures;
- identical position-local input contract;
- constructor, fit, and predict argument rejection;
- per-model failure isolation;
- prediction shape and finite-value validation;
- campaign minimum-history enforcement;
- raw pandas frame immutability;
- fake-runtime matrix smoke;
- Python compile and AST parsing;
- YAML parsing and 100-character line inspection.

Not executed:

- installation or import of `darts==0.46.1`;
- real ARIMA/AutoARIMA/ExponentialSmoothing/Theta/Croston fitting;
- real OOF accuracy or baseline superiority;
- real model persistence;
- Torch, CUDA, GPU PID, VRAM, or CPU fallback certification.
