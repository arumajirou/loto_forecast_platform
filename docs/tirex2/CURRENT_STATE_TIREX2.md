# TiRex-2 current state

Status: `PARTIALLY_VERIFIED / CONTRACT_V2_IMPLEMENTED / RUNTIME_NOT_EXECUTED`

The legacy provider is fixed to seven `n1...n7` columns and returns only q0.5 at the first
horizon. The new isolated path introduces arbitrary geometry, target count, horizons 1/2/5,
full q0.1-q0.9 retention, fail-closed future covariates, exact package/model provenance, and
explicit CUDA fallback rejection.

The two-process reload certifier is implemented and hermetically tested. Real TiRex-2 package
loading, CPU/GPU inference, real separate-process reproduction, covariates, OOF, Holdout, and
Prospective evaluation remain unverified in this change.
