# AutoFreTS Runtime Test Plan

## Contract tests

- reject unknown fields and type coercion;
- require portable Run IDs and absolute work directories;
- require 40-character source revision and 64-character source digest;
- enforce CPU/GPU profile and device consistency;
- enforce fixed `precision=32-true`;
- enforce sufficient history for the resolved input window;
- require finite rectangular point output;
- require all lifecycle flags for PASS;
- require backend evidence for Ray and Optuna;
- reject GPU evidence on CPU requests;
- require PID, UUID, positive VRAM, and external samples on CUDA;
- require `fft_dtype=float32`;
- require channel-frequency mixing to remain disabled;
- require exact parameter-count equality.

## Source-identity tests

- deterministic 10-file ordered source inventory;
- digest changes when any source byte changes;
- exact Git HEAD equality;
- non-detached branch requirement;
- clean tracked, staged, and untracked state;
- symlink rejection;
- byte-exact snapshot materialization;
- copied size and SHA-256 revalidation.

## Adapter tests

- model identity maps to `nf-local-auto-frets`;
- source-tree digest becomes configuration identity;
- expected output shape is `[1, horizon]`;
- commands use argv arrays without shell interpolation;
- CPU commands hide CUDA;
- Ray temporary paths stay outside the repository;
- worker responses map to common RunObservation and DeviceEvidence;
- source revision, source digest, package version, and mode drift fail closed;
- blocked execution writes structured failure evidence and seals the result.

## Worker tests

- deterministic synthetic float32 input;
- exact horizon extraction;
- PID-scoped `nvidia-smi` parsing;
- FreTS model discovery through nested AutoModel wrappers;
- all parameters are float32;
- exact architecture parameter formula;
- temporal FFT-bin evidence;
- channel-frequency mixing remains false;
- save/load replay difference stays within tolerance.

## Target-host runtime matrix

Run serially after PR #123 and PR #149 are available in one clean checkout:

| Stage | Mode | Device | Required result |
|---|---|---|---|
| 1 | direct | CPU | CPU_SMOKE PASS |
| 2 | ray | CPU | CPU_SMOKE PASS |
| 3 | optuna | CPU | CPU_SMOKE PASS |
| 4 | direct | CUDA | GPU_FORMAL PASS |
| 5 | ray | CUDA | GPU_FORMAL PASS or honest blocker |
| 6 | optuna | CUDA | GPU_FORMAL PASS or honest blocker |

Do not start a multi-seed search campaign from partial runtime evidence.

## Deferred evaluation

- chronological Train/Validation/OOF execution;
- multiple seeds with mean, variance, and worst values;
- Hit@±1-first comparison against Random, fixed, mean, median, last,
  frequency, and statistical baselines;
- Holdout;
- prediction locking before Prospective actuals;
- public registration and promotion.
