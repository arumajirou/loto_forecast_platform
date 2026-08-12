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

## Process-evidence follow-up

A later exact-head run on `7eff195de88f0786420c5a1ca40b284b75234d50` (`pr263-process-evidence-20260812-082542`) verified the remaining process-attribution mechanics except numeric per-task VRAM:

```text
model runtime success         = 4/4
matrix complete               = true
scheduler invariants          = PASS
actual child PID              = PASS 4/4
process observation file      = PASS 4/4
positive peak RSS             = PASS 4/4
GPU PID attribution           = PASS 3/3 GPU models
CPU fallback classification   = PASS
all leases released           = true
top-level SHA-256             = PASS
nested SHA-256                = PASS
```

Observed process evidence:

| Model | Child PID | Peak RSS MiB | GPU PID |
|---|---:|---:|---:|
| `sf-autoarima` | 560452 | 247.7578125 | N/A |
| `nfauto-rnn` | 560453 | 2030.36328125 | 560453 |
| `nf-dlinear` | 560454 | 1615.875 | 560454 |
| `nf-timellm` | 561022 | 4018.87109375 | 561022 |

The WSL `nvidia-smi --query-compute-apps=pid,used_memory` path returned valid compute PIDs but did not provide numeric per-process `used_memory`, so `peak_gpu_memory_mib` remained null in the generic process observer.

## VRAM evidence scan correction

The first post-run JSON scan reported `NO_NUMERIC_PEAK_FOUND`, but that scan used an overly narrow key regex and therefore produced a false negative for TimeLLM. The TimeLLM smoke contract already writes process-local PyTorch allocator values under:

```text
cuda_peak_allocated_mib
cuda_peak_reserved_mib
```

in `timellm-smoke/RESULT.json`.

Therefore the current state is **not** “0/3 GPU models have numeric VRAM evidence”. The immutable artifact must be rescanned with a pointer-aware rule that recognizes any numeric key/path containing `peak` plus CUDA/GPU/VRAM memory semantics. No new monitor should be implemented until that corrected scan is complete.

For standard NeuralForecast campaign tasks, the stacked PR #260 lineage already contains process-local CUDA allocator primitives such as `cuda_peak_memory_allocated` and phase baseline/delta evidence. Those values were not confirmed in the representative broad-campaign artifacts and must not be assumed present without artifact evidence.

## Remaining runtime-certification gap

Issue #264 remains open until numeric per-task GPU-memory evidence is resolved for the representative GPU profiles and exact-head CI status is known.

If the corrected artifact scan confirms numeric evidence only for TimeLLM, the next fallback should be limited to the missing ordinary GPU models. Any device-total VRAM fallback must run those GPU tasks in isolation and explicitly record the verification method, baseline, peak, delta, and absence of unrelated compute PIDs so that concurrent device memory cannot be misattributed.
