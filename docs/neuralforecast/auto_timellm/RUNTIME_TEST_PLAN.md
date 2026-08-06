# AutoTimeLLM Runtime Certification Test Plan

## Focused contract tests

1. Canonical request SHA-256 is deterministic.
2. CPU and GPU profile/device mismatches fail closed.
3. Insufficient history for the selected architecture fails closed.
4. CPU PASS responses reject GPU evidence.
5. Non-finite worker outputs fail validation.
6. Deterministic synthetic input is seed-stable and bounded.
7. `nvidia-smi` parsing retains only the exact provider PID.
8. Common identity conversion preserves model, revision, config, weight, and artifact roles.
9. Worker commands use explicit argv without shell interpolation.
10. CPU worker responses map to provider-neutral observations.
11. Provider execution failures are sealed as structured BLOCKED evidence.

These focused tests use a dependency-light compatibility stub for the parent PR #126 contracts and an
interface double for PR #123. They do not execute NeuralForecast, Transformers, Ray, an LLM, or CUDA.

## Target-host CPU gate

- exact `neuralforecast==3.2.0`;
- reviewed immutable snapshot and complete SHA-256 inventory;
- two distinct real worker processes;
- fit, predict, save, load, and re-predict all succeed;
- exact output shape `[1, horizon]` and finite values;
- replay difference is within the declared tolerance;
- CPU requested and effective;
- no GPU evidence and no CPU fallback;
- complete report, SHA256SUMS, ZIP, and ZIP sidecar verify.

## Target-host GPU gate

Run only after CPU passes. In addition to the CPU lifecycle:

- CUDA available and requested;
- effective model parameter device is CUDA;
- worker PID equals provider GPU PID;
- positive peak VRAM;
- matching external `nvidia-smi` PID/UUID/memory evidence;
- PID release after exit;
- two distinct real processes;
- no CPU fallback.

## Repository validation order

```text
focused tests
→ compileall and AST
→ shell syntax
→ Ruff changed paths
→ mypy changed modules
→ related regression tests
→ full pytest and coverage
→ one actionable GitHub Actions run
```

A workflow with no created steps or logs is `CI_BLOCKED_PRE_RUN`, not code success or failure.

## Accuracy boundary

Runtime certification never opens project evaluation data. A separate later evaluation must preserve
chronological Train, Validation, Holdout, and Prospective boundaries; Train-only HPO; multiple seeds;
Hit@±1 as primary; MAE, MSE, RMSE, position/all-position metrics; and required baselines.
