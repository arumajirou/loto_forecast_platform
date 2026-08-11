# Resource-Aware Runtime Audit

## Scope

This document defines the runtime-availability audit surface added for the broad catalog.
It is not an accuracy, Holdout, Prospective, or promotion protocol.

The broad catalog currently contains 174 model identities. A model identity is not an
execution count. With the six canonical games, the broad matrix contains:

```text
174 models x 6 games = 1,044 model-game execution units
```

Seeds, folds, HPO trials, parameter variants, backends, and provider revisions expand the
execution count further and must remain explicit dimensions rather than being folded into a
single misleading "model count".

## Resource planning

`loto.orchestration.resource_scheduler.collect_resource_snapshot()` captures:

- logical CPU count;
- available RAM from `/proc/meminfo` when available;
- GPU count;
- per-GPU total and free VRAM from `nvidia-smi`.

`resolve_resource_plan()` derives conservative CPU and GPU outer concurrency from the live
snapshot and configured safety policy. The default planner uses:

- outer worker cap: 8;
- 2 CPU threads per CPU job;
- 6 GiB available RAM budget per CPU job;
- 5 GiB estimated VRAM slot for ordinary GPU jobs;
- 2 GiB GPU safety margin.

These are scheduling budgets, not claims about a model's measured peak resources.
Measured model profiles should replace estimates when certified evidence is available.

## Resource classes

Current classes are:

- `CPU`: no GPU lease is required;
- `GPU`: consumes one ordinary GPU lease;
- `EXCLUSIVE_GPU`: consumes all configured GPU leases for the duration of the task.

`nf-timellm` / `TimeLLM` is explicitly `EXCLUSIVE_GPU` because the broad default campaign
was observed to saturate a 16 GB RTX 5070 Ti and time out. The exclusive classification is a
safety rule, not an accuracy or runtime-certification claim.

## TimeLLM reduced runtime contract

`scripts/run_timellm_safe_smoke.py` provides a separate, reduced runtime-smoke contract for
16 GB RTX-class GPUs. Its defaults are intentionally distinct from the unified campaign:

- `precision=bf16-mixed`;
- `batch_size=1`;
- `valid_batch_size=1`;
- `windows_batch_size=8`;
- `inference_windows_batch_size=8`;
- `input_size=32`;
- `d_ff=64`;
- `d_model=16`;
- `n_heads=4`;
- `h=1`;
- `max_steps=5` by default.

The reduced smoke records load, fit, predict, finite-output status, raw game-domain status,
PyTorch peak allocated/reserved CUDA memory, environment evidence, predictions, and SHA-256
checksums.

A reduced TimeLLM smoke result must never replace the original unified-campaign result. The
two executions have different configuration identities and execution contracts.

## Broad resource-aware runner

Plan all 174 identities across all six games without executing:

```bash
uv run python scripts/run_resource_aware_broad_campaign.py \
  --plan-only \
  --models all \
  --games all \
  --output runs/broad-plan-$(date +%Y%m%d-%H%M%S)
```

Expected current matrix size:

```text
catalog_models = 174
model_game_pairs = 1044
```

Execute the matrix using live resource-derived CPU/GPU concurrency:

```bash
uv run python scripts/run_resource_aware_broad_campaign.py \
  --models all \
  --games all \
  --outer-worker-cap 8 \
  --output runs/broad-resource-aware-$(date +%Y%m%d-%H%M%S)
```

The runner creates separate CPU and GPU executors and uses `ResourceScheduler` leases to
prevent ordinary GPU jobs from overlapping an `EXCLUSIVE_GPU` task.

## Evidence artifacts

Top-level artifacts include:

- `RESOURCE_SNAPSHOT.json`;
- `RESOURCE_PLAN.json`;
- `MATRIX_PLAN.json`;
- `RESULTS.jsonl`;
- `SUMMARY.json`;
- `RESOURCE_LEASES.json`;
- `SHA256SUMS`.

Each model-game case receives its own immutable attempt directory with command, stdout,
stderr, campaign or TimeLLM-smoke evidence, and `FINAL.json`.

The campaign output directory is never pre-created before `loto3 campaign`; this preserves
the fail-closed immutable-output contract.

## Status interpretation

A subprocess return code is not a model-runtime decision by itself.

Examples:

- `SUCCEEDED`: the selected catalog row completed successfully under the unified campaign;
- `FAILED`: the campaign produced an explicit model failure row;
- `UNAVAILABLE`: dependency/runtime is unavailable;
- `NOT_ROUTABLE`: the broad entry has no route on this execution surface;
- `UNSUPPORTED_GAME`: the model contract rejects this game geometry;
- `NON_STANDALONE_METHOD`: reconciliation/method entry is not a standalone forecaster;
- `POST_RUN_SERIALIZATION_FAILED`: model fit/predict evidence reached summary serialization,
  but the summary could not be written;
- `TIMEOUT`: the execution exceeded its configured wall-clock limit;
- `RUNTIME_SMOKE_SUCCEEDED`: the separate reduced TimeLLM runtime contract completed;
- `BLOCKED_GPU_RESOURCE`: no safe GPU slot was resolved from the live resource snapshot.

`RUNTIME_SMOKE_SUCCEEDED` is not equivalent to game compatibility, runtime certification,
accuracy validation, or promotion.

## NeuralForecast MAE serialization remediation

The broad audit demonstrated a shared post-run failure in which NeuralForecast models could
complete CUDA fit and predict and then fail while serializing runtime metadata containing
`MAE()`.

Canonical JSON now has a deliberately narrow fallback for the observed
`neuralforecast.losses.*.MAE` object. It emits only the qualified Python type marker. Other
arbitrary Python objects still raise `TypeError` so formal protocol evidence cannot silently
accept uncontrolled runtime objects.

## Scientific boundaries

This runtime audit keeps the following gates closed:

- Holdout evaluation;
- Prospective evaluation;
- champion promotion;
- future-predictability claims;
- statistical-superiority claims.

Formal evaluation still requires chronological Train/Validation/Holdout/Prospective
separation, prediction locking before actuals, all configured seeds, Hit@±1 as the primary
metric, secondary error metrics, mandatory baselines, and runtime certification evidence.
