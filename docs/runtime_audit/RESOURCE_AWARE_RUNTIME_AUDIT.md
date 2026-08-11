# Resource-Aware Runtime Audit

## Scope

This document defines the runtime-availability audit surface added for the broad catalog.
It is not an accuracy, Holdout, Prospective, or promotion protocol.

The broad catalog currently contains 174 model identities. The collision-free unified catalog
currently contains 250 canonical identities: 174 broad identities plus 76 probabilistic
identities. A model identity is not an execution count.

With the six canonical games, the planning upper bounds are currently:

```text
broad:   174 models x 6 games = 1,044 model-game execution units
unified: 250 models x 6 games = 1,500 model-game execution units
```

Seeds, folds, HPO trials, parameter variants, backends, and provider revisions expand the
execution count further and must remain explicit dimensions rather than being folded into a
single misleading "model count".

Provider scripts and NeuralForecast local extensions are execution surfaces, not automatically
additional canonical identities. They must be recursively inventoried and de-duplicated before
being added to the unified identity count.

## Observed planning evidence — 2026-08-11

On Linux/WSL at branch head `3cc8bc75bad36c8467c8297f9e21eb03e4a41276`, the identity
planner reported:

```text
broad_catalog_identities          = 174
probabilistic_catalog_identities  = 76
unified_catalog_identities        = 250
probabilistic_native_identities   = 76
provider_script_count             = 32
neuralforecast_local_extensions   = 4
broad_model_game_cross_product    = 1044
unified_model_game_cross_product  = 1500
```

The same host reported 32 logical CPUs, 59,355 MiB available RAM, one RTX 5070 Ti with
16,303 MiB total VRAM and 15,705 MiB free VRAM. With the default scheduling budgets and
`outer_worker_cap=8`, the resolved plan was:

```text
parallel_cpu_models           = 6
parallel_gpu_models           = 2
parallel_exclusive_gpu_models = 1
cpus_per_trial                = 2
gpu_slot_mib                  = 5120
safety_margin_mib             = 2048
```

These values are evidence for that snapshot only. The runner re-resolves them from live
resources on each run.

## Development-tool verification prerequisite

`ruff` and `pytest` are declared in the project's optional `dev` extra, not in the default
runtime dependency set. A plain `uv run ruff` or `uv run pytest` can therefore fail with
`Failed to spawn` when the dev extra has not been synced. That is an environment/tooling
precondition failure, not a source-code test failure.

Use either:

```bash
uv sync --extra dev
uv run ruff check <paths...>
uv run pytest -q <paths...>
```

or run the tools without a persistent sync:

```bash
uv run --extra dev ruff check <paths...>
uv run --extra dev pytest -q <paths...>
```

Use `uv run python` (or `python3`) for inline Python checks on hosts that do not provide a
`python` shell alias.

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

Plan the current broad identities across all six games without executing:

```bash
uv run python scripts/run_resource_aware_broad_campaign.py \
  --plan-only \
  --models all \
  --games all \
  --output runs/broad-plan-$(date +%Y%m%d-%H%M%S)
```

The current expected matrix is derived from the live registry rather than a typed constant.
At the 2026-08-11 snapshot it was 174 broad identities and 1,044 model-game pairs.

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
