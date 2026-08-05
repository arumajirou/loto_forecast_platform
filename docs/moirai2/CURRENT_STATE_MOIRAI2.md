# Current State: Moirai 2.0

Status: `PARTIALLY_VERIFIED / P0_P8_IMPLEMENTED / REAL_UNI2TS_RUNTIME_PENDING`.

PR #83 provides P0-P6 Contract v2 and PR #86 provides P7 native covariate wiring. P8 adds an
isolated runtime-certification harness without changing shared workers, catalogs, root dependencies,
common CLI, workflows, the top-level README, Moirai 1.x, Moirai-MoE, or other TSFM providers.

P8 runs the same immutable request and explicit pinned snapshot in two separate provider processes.
It compares point output and all nine native quantiles by canonical SHA-256, verifies model and
covariate artifact identity, observes forward input/output tensor devices, and records external GPU
PID, UUID, VRAM, and post-exit PID release evidence when CUDA is requested.

Local pure and fake-boundary verification has passed. No real Uni2TS snapshot load, real predictor
execution, real CUDA observation, full repository test, or successful GitHub Actions run is claimed.
