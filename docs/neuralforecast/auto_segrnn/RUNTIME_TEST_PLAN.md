# AutoSegRNN Runtime Test Plan

## Contract tests

- reject unknown fields and type coercion;
- require portable Run IDs and absolute work directories;
- require a 40-character source revision and 64-character source digest;
- enforce CPU/GPU profile and precision consistency;
- enforce history length against resolved architecture geometry;
- require finite rectangular point output;
- require complete lifecycle evidence for PASS;
- require backend execution evidence for Ray and Optuna;
- reject GPU evidence on CPU requests;
- require matching GPU PID, UUID, positive VRAM, and external samples on CUDA.

## Source-identity tests

- deterministic ordered source inventory;
- combined digest changes when any source byte changes;
- exact Git HEAD equality;
- non-detached branch requirement;
- clean tracked, staged, and untracked state;
- symlink rejection;
- byte-exact source snapshot materialization;
- copied size and SHA-256 revalidation.

## Adapter tests

- local model identity maps to the common SDK;
- source-tree digest is retained as model configuration identity;
- source snapshot revision equals model revision;
- output contract is exactly `[1, horizon]`;
- command uses an argv array and no shell interpolation;
- CPU command hides CUDA;
- Ray temporary paths remain outside the repository;
- worker response maps to common RunObservation and DeviceEvidence;
- source revision, source digest, package version, and execution mode drift fail closed;
- blocked execution writes structured failure evidence and seals the result.

## Target-host runtime matrix

Execute serially after PR #123 and PR #136 are available in one clean checkout:

| Stage | Mode | Device | Required result |
|---|---|---|---|
| 1 | direct | CPU | CPU_SMOKE PASS |
| 2 | ray | CPU | CPU_SMOKE PASS |
| 3 | optuna | CPU | CPU_SMOKE PASS |
| 4 | direct | CUDA | GPU_FORMAL PASS |
| 5 | ray | CUDA | GPU_FORMAL PASS or documented blocker |
| 6 | optuna | CUDA | GPU_FORMAL PASS or documented blocker |

Do not start the full search campaign from partial runtime evidence.

## Required formal checks

- exact `neuralforecast==3.2.0`;
- exact clean Git commit;
- source-tree SHA-256 equality in parent and both workers;
- two distinct provider PIDs;
- fit and prediction success;
- exact output shape and finite values;
- save/load/re-predict success;
- same-process reload difference within tolerance;
- cross-process replay within tolerance;
- requested/effective device equality;
- no CPU fallback;
- provider PID, GPU UUID, positive VRAM, external process sample, and release on CUDA;
- complete artifact manifest, SHA256SUMS, ZIP, and ZIP sidecar.

## Deferred tests

- chronological OOF on project data;
- multiple search seeds and mean/variance/worst aggregation;
- Hit@±1-first comparison against Random, fixed, mean, median, last, frequency,
  and statistical baselines;
- Holdout evaluation;
- Prospective prediction locking before actuals;
- public registration and production promotion.
