# Runtime Audit Evidence Ledger — 2026-08-11

## Purpose

This file is the durable, version-controlled evidence ledger for the runtime-audit remediation work tracked in PR #263 and Linear TAJ-15.

It records observed execution results and their interpretation. It is **not** an accuracy, Holdout, Prospective, or promotion report. A runtime `SUCCEEDED` result does not imply predictive superiority.

## Evidence rules

- Preserve the exact source head for every meaningful run.
- Distinguish model execution failures from harness, serialization, dependency, resource, or orchestration failures.
- Do not treat catalog registration as runtime certification.
- Holdout and Prospective remain closed unless explicitly stated otherwise.
- Do not infer GPU child-process identity from the scheduler PID.
- Keep reduced TimeLLM smoke results separate from broad/default TimeLLM campaign results.

## 1. Broad 174 runtime audit baseline

Source lineage used for the broad audit:

```text
5eb722e01271e20b079f4b243e9dd5c75b8b819c
```

The one-by-one broad audit attempted all 174 broad catalog entries and completed its execution-attempt matrix.

Canonical model-level normalization of the raw campaign results was:

| Status | Count |
|---|---:|
| SUCCEEDED | 38 |
| FAILED | 60 |
| POST_RUN_SERIALIZATION_FAILED | 24 |
| TIMEOUT | 1 |
| UNAVAILABLE | 21 |
| NOT_ROUTABLE | 19 |
| NON_STANDALONE_METHOD | 10 |
| UNSUPPORTED_GAME | 1 |
| **Total** | **174** |

Important correction: the 24 `POST_RUN_SERIALIZATION_FAILED` NeuralForecast cases had already reached model fit/predict evidence and then failed while serializing campaign summary data containing a NeuralForecast `MAE` object. They must not be counted as model runtime failures.

The single broad TimeLLM run timed out under the broad/default-like profile. A separate reduced BF16 smoke later proved that a constrained TimeLLM profile can load, fit, and predict on the RTX 5070 Ti. Those two execution contracts remain separate.

## 2. Identity inventory

Observed inventory on 2026-08-11:

```text
broad catalog identities          174
probabilistic catalog identities   76
unified canonical identities      250
probabilistic native identities    76
canonical games                     6
broad model-game pairs           1044
unified model-game pairs         1500
provider scripts                   32
NeuralForecast local extensions     4
```

The 32 provider scripts and four local extensions are execution surfaces. They are not blindly added to the canonical identity count without de-duplication.

## 3. Initial resource plan

Observed host snapshot:

```text
logical CPUs        32
available RAM       59,355 MiB
GPU                  1 x RTX 5070 Ti
GPU total VRAM      16,303 MiB
GPU free VRAM       15,705 MiB
```

Initial conservative plan with `gpu_slot_mib=5120` and `outer_worker_cap=8`:

```text
parallel CPU models            6
parallel GPU models            2
parallel exclusive GPU models  1
cpus per trial                 2
GPU slot                       5,120 MiB
GPU safety margin              2,048 MiB
```

This plan was safe but too conservative for light NeuralForecast Auto smoke workloads. It caused GPU-heavy sections of the broad run to appear effectively two-way parallel.

## 4. Three-lane smoke

The three-lane runtime smoke exercised:

```text
sf-autoarima   -> CPU
nf-dlinear     -> ordinary GPU
nf-timellm     -> EXCLUSIVE_GPU
```

Observed result:

```text
sf-autoarima::numbers4  SUCCEEDED
nf-dlinear::numbers4    SUCCEEDED
nf-timellm::numbers4    RUNTIME_SMOKE_SUCCEEDED
```

The CPU and ordinary GPU tasks overlapped. TimeLLM waited for the ordinary GPU lease to release and then acquired the exclusive GPU capacity.

## 5. All-game three-model smoke and Lightning race

A 3-model x 6-game run produced 18 execution units.

Initial result:

```text
17/18 execution success
nf-dlinear::bingo5 FAILED
```

The failure was not a DLinear/Bingo5 incompatibility. The failure traceback showed a PyTorch Lightning logging race:

```text
FileExistsError: [Errno 17] File exists: '.../lightning_logs/version_*'
```

The same `nf-dlinear / bingo5 / seed=1` succeeded in isolated reproduction.

Classification:

```text
MODEL_GAME_INCOMPATIBILITY = NO
LIGHTNING_SHARED_LOG_RACE  = YES
```

## 6. Runtime-workdir isolation regression

Per-attempt working-directory isolation removed the shared Lightning log race, but the first implementation moved the whole `loto3 campaign` subprocess outside the repository.

That caused 12 ordinary campaign tasks to fail before model execution because Git provenance used:

```text
git rev-parse HEAD
```

from a non-repository current working directory.

The fix changed Git provenance resolution to use the repository root explicitly while retaining per-attempt runtime working directories for Lightning isolation.

## 7. Post-fix 18/18 verification

Exact source head:

```text
c403dbd0e10e9ef2ff514fc142108ff3fa428ebf
```

Observed verification:

```text
Ruff                         PASS
focused pytest               12/12 PASS
matrix                       18/18
sf-autoarima                 6/6 SUCCEEDED
nf-dlinear                   6/6 SUCCEEDED
nf-timellm                   6/6 RUNTIME_SMOKE_SUCCEEDED
git rev-parse cwd failure    0
Lightning FileExistsError    0
released_at                  non-null for all 18
SHA256SUMS                   PASS
```

This closed both orchestration defects together: shared Lightning logging collisions and Git provenance lookup from the wrong cwd.

## 8. Six-way GPU concurrency proof

Exact source head:

```text
c403dbd0e10e9ef2ff514fc142108ff3fa428ebf
```

Models:

```text
nfauto-rnn
nfauto-lstm
nfauto-gru
nfauto-tcn
nfauto-deepar
nfauto-dilatedrnn
```

Configuration:

```text
gpu_slot_mib        = 2048
gpu safety margin   = 2048 MiB
outer worker cap    = 8
resolved GPU slots  = 6
```

All six GPU leases started within approximately 2 ms and all six models completed successfully.

Observed concurrency:

```text
PEAK_SIMULTANEOUS_GPU_TASKS = 6
GPU_PARALLELISM             = PASS
status                      = 6/6 SUCCEEDED
```

This is direct evidence that these six specific NeuralForecast Auto smoke profiles can execute six-way concurrently on the tested RTX 5070 Ti configuration. It is not evidence that every GPU model is safe at a 2 GiB reservation.

## 9. Global eight-way concurrency proof

Exact source head:

```text
c403dbd0e10e9ef2ff514fc142108ff3fa428ebf
```

CPU tasks:

```text
sf-autoarima
sf-naive
```

GPU tasks:

```text
nfauto-rnn
nfauto-lstm
nfauto-gru
nfauto-tcn
nfauto-deepar
nfauto-dilatedrnn
```

Observed lease concurrency:

```text
PEAK_TOTAL_TASKS = 8
PEAK_GPU_TASKS   = 6
PEAK_CPU_TASKS   = 2
GPU_6WAY         = PASS
CPU_2WAY         = PASS
GLOBAL_8WAY      = PASS
```

All eight tasks completed `SUCCEEDED` and SHA-256 verification passed.

The evidence demonstrates real eight-task overlap, not merely an `outer_worker_cap=8` configuration value.

## 10. Weighted/adaptive scheduler staging

Weighted scheduler implementation was staged on PR #263 after the eight-way proof.

Intended evidence-first policy:

```text
CPU             CPU/RAM governed
GPU_LIGHT       1 base slot
GPU_MEDIUM      2 base slots
GPU_HEAVY       3 base slots
EXCLUSIVE_GPU   all resolved GPU slots
```

Only the six NeuralForecast Auto models proven in the six-way smoke are initially classified `GPU_LIGHT`.

Other NeuralForecast models remain `GPU_MEDIUM` until measured. Unknown GPU-capable models remain `GPU_HEAVY`. TimeLLM, TSFM, foundation, and zero-shot profiles remain `EXCLUSIVE_GPU` until independently profiled.

## 11. Current weighted-scheduler validation status

Current local head tested:

```text
a171d438ed3e3e59797685709c8c865f5f5a7adf
```

The first focused validation did **not** pass cleanly because Ruff found one fixable import-style error:

```text
UP035 Import from collections.abc instead: Iterable
src/loto/orchestration/weighted_resource_scheduler.py
```

Therefore the weighted scheduler is currently:

```text
IMPLEMENTED                  YES
FOCUSED_RUFF                 FAIL (1 fixable UP035)
FOCUSED_MYPY                 NOT CONFIRMED IN THIS RUN
FOCUSED_PYTEST               NOT CONFIRMED IN THIS RUN
MIXED_WEIGHTED_RUNTIME_SMOKE NOT EXECUTED
```

The subsequent mixed weighted smoke attempt was launched after entering a new WSL shell whose cwd was:

```text
/mnt/c/Windows/System32
```

The command failed before runner startup with:

```text
can't open file '/mnt/c/Windows/System32/scripts/run_weighted_resource_aware_broad_campaign.py'
```

All missing `RESOURCE_PLAN.json`, `RESOURCE_LEASES.json`, `RESULTS.jsonl`, and `SHA256SUMS` messages from that attempt are secondary consequences of the runner never starting. They are **not** weighted-scheduler runtime failures.

## 12. GPU idle snapshot before weighted validation

At approximately 2026-08-11 21:11 JST, `nvidia-smi` reported:

```text
RTX 5070 Ti
288 MiB / 16,303 MiB VRAM
30% GPU utilization
No running compute processes found
```

This is an idle/pre-test snapshot and must not be used as peak VRAM evidence for a model run.

## 13. Remaining evidence gaps

The current scheduler lease `pid` represents the scheduler process rather than the actual child `loto3` process. Weighted lease output now distinguishes `scheduler_pid` and reserves `child_pid`, but child PID/process-tree collection is not yet complete.

Required before formal runtime certification:

```text
actual child PID
process tree
per-task peak RSS
per-task GPU PID mapping when available
per-task peak VRAM
GPU utilization trace
CPU fallback evidence
save/reload/predict evidence where required
finite output / output-shape evidence
```

## 14. Current gate

Do **not** start the full 1,044 broad model-game sweep with the weighted runner yet.

Next gate:

1. fix the single Ruff `UP035` import;
2. rerun Ruff, mypy, and focused pytest from the repository root;
3. run the mixed CPU + GPU_LIGHT + GPU_MEDIUM + EXCLUSIVE_GPU smoke from the repository root;
4. verify slot accounting and exclusive-GPU non-overlap;
5. only then promote the weighted scheduler into the full broad runtime audit path.

## Scientific boundary

Nothing in this ledger establishes predictive accuracy or promotion eligibility.

```text
Holdout evaluated     = false
Prospective evaluated = false
Promotion             = false
```

Runtime success and concurrency evidence must remain separate from Hit@±1, MAE, MSE, RMSE, baseline superiority, and prospective prediction claims.
