# Weighted Mixed Runtime Smoke — 2026-08-12

## Scope

This file records the exact evidence for the representative weighted CPU/GPU mixed runtime smoke used by PR #263 and Issue #264.

It is runtime/orchestration evidence only. It is **not** Holdout, Prospective, accuracy-superiority, or promotion evidence.

## Exact source identity

```text
source_head = 896d5030dcdf4e672f989075a7eb337fbebc4c34
run_id      = pr263-weighted-mixed-20260812-080107
artifact    = /mnt/e/env/ts/loto-validation/pr263-weighted-mixed-20260812-080107
```

The remote branch head and detached validation worktree both matched the exact source head before execution.

## Environment

Observed runtime preflight:

```text
Python            3.13.14
uv                0.11.21
Torch             2.9.1+cu128
CUDA available    true
CUDA runtime      12.8
GPU               NVIDIA GeForce RTX 5070 Ti
GPU total VRAM    16,303 MiB
GPU free VRAM     15,729 MiB before the run
```

## Representative matrix

The smoke executed one Numbers4 unit for each representative resource profile:

| Model | Library | Weighted profile | Slots | Terminal status |
|---|---|---:|---:|---|
| `sf-autoarima` | StatsForecast | `CPU` | 1 | `SUCCEEDED` |
| `nfauto-rnn` | NeuralForecast Auto | `GPU_LIGHT` | 1 | `SUCCEEDED` |
| `nf-dlinear` | NeuralForecast | `GPU_MEDIUM` | 2 | `SUCCEEDED` |
| `nf-timellm` | NeuralForecast | `EXCLUSIVE_GPU` | 6 | `RUNTIME_SMOKE_SUCCEEDED` |

Resolved resource plan:

```text
parallel_cpu_models            2
parallel_gpu_models            6
parallel_exclusive_gpu_models  1
cpus_per_trial                 2
gpu_slot_mib                   2048
safety_margin_mib              2048
outer_worker_cap               8
```

## Scheduler timing evidence

Observed leases:

```text
sf-autoarima  CPU           start=1786489280.2074137  release=1786489283.0646403
nf-timellm    EXCLUSIVE_GPU start=1786489280.2075796  release=1786489292.5312550
nfauto-rnn    GPU_LIGHT     start=1786489292.5313840  release=1786489324.8285842
nf-dlinear    GPU_MEDIUM    start=1786489292.5317304  release=1786489298.6938584
```

Derived invariants:

```text
CPU_WITH_GPU_OVERLAP       = true
LIGHT_MEDIUM_OVERLAP       = true
EXCLUSIVE_LIGHT_OVERLAP    = false
EXCLUSIVE_MEDIUM_OVERLAP   = false
all leases released        = true
scheduler error count      = 0
matrix complete            = true
model runtime success      = 4/4
```

Interpretation:

- `EXCLUSIVE_GPU` correctly reserved all six resolved GPU slots.
- CPU execution was allowed to overlap with the exclusive GPU task; exclusive means GPU-exclusive, not host-exclusive.
- `GPU_LIGHT` and `GPU_MEDIUM` were admitted immediately after the exclusive lease released and overlapped while consuming 1 + 2 of the six GPU slots.
- No ordinary GPU lease overlapped the exclusive GPU lease.

## Runtime outcome evidence

```text
sf-autoarima  SUCCEEDED
nfauto-rnn    SUCCEEDED
nf-dlinear    SUCCEEDED
nf-timellm    RUNTIME_SMOKE_SUCCEEDED
```

TimeLLM used the separate reduced GPU runtime-smoke contract. Its result remained `PENDING_DECODE_OR_CALIBRATION` for game compatibility and therefore must not be interpreted as accuracy or promotion evidence.

## Integrity evidence

Top-level and nested `SHA256SUMS` verification passed for the resource plan/snapshot, matrix, results, leases, campaign evidence, prediction locks, protocols, TimeLLM smoke evidence, and logs.

The final observed GPU state was:

```text
NVIDIA GeForce RTX 5070 Ti, 16303 MiB total, 306 MiB used, 15690 MiB free
```

## Scientific gates

```text
Holdout evaluated      = false
Prospective evaluated  = false
Promotion               = false
```

## Remaining runtime-certification gap

This smoke does **not** close Issue #264 completely.

All four leases reported:

```text
child_pid = null
```

Therefore the following evidence remains required before the scheduler/runtime certification gate can be considered complete:

- actual spawned child PID;
- process-tree capture;
- per-task peak RSS;
- GPU process/PID attribution;
- per-task peak GPU memory evidence for ordinary GPU jobs;
- explicit CPU-fallback verification where fallback is supported/expected;
- tests proving process-observation evidence survives success, nonzero exit, and timeout paths.

The next implementation step is to replace the opaque `subprocess.run()` execution path with a monitored `Popen`-based helper that records those fields without changing model/evaluation semantics.
