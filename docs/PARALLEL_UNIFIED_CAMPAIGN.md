# Parallel unified campaign execution

Status: implementation support for development-only Unified Campaign execution.

This feature does not open Holdout, Prospective, or promotion gates. It only changes how independent game workloads are scheduled.

## Why

The original `loto3 campaign` loop evaluates games sequentially. Real-data validation on the six canonical games showed that the game workloads are independent and can be executed concurrently while preserving the existing per-game chronological folds, prediction locks, metrics, baselines, and protocol artifacts.

The parallel runner therefore partitions by **game**, not by target row. Each game still uses the existing `run_unified_campaign()` implementation unchanged inside its worker process.

## Run six games in parallel

```bash
RUN_ID="parallel-$(date +%Y%m%d-%H%M%S)"
OUT="artifacts/unified-campaign/${RUN_ID}"

uv run python -m loto.evaluation.parallel_campaign run \
  --input-dir /absolute/path/to/canonical-csv-directory \
  --output "$OUT" \
  --games mini,loto6,loto7,bingo5,numbers3,numbers4 \
  --workers 6 \
  --reserve-cpus 2 \
  --seeds 1 \
  --folds 3 \
  --test-size 20 \
  --min-train-size 100 \
  --holdout-size 50 \
  --device cpu
```

`--workers 1` delegates to the existing sequential `run_unified_campaign()` path.

On Linux, workers use CPU affinity when available. BLAS/OpenMP/loky thread limits are also set per worker to reduce nested oversubscription. On platforms without CPU-affinity support, the same parallel-by-game process model is used without affinity pinning.

## Live progress from another terminal

```bash
uv run python -m loto.evaluation.parallel_campaign status \
  --root "$OUT" \
  --watch \
  --interval 2 \
  --hardware
```

The status view reads only campaign artifacts. It does not mutate the running campaign.

During execution it shows:

- overall model × game lower-bound progress;
- per-game progress;
- worker/game terminal status;
- optional NVIDIA GPU telemetry when `nvidia-smi` is available.

A model that terminates without a prediction lock (for example `NOT_ROUTABLE`) may make the in-flight progress a conservative lower bound. When a per-game `campaign_summary.json` is written, that game's progress becomes exact. The final root summary is exact.

## Output layout

Parallel runs write a root aggregate plus isolated game sub-runs:

```text
campaign-plan.json
progress.json
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
SHA256SUMS
games/
  mini/
  loto6/
  loto7/
  bingo5/
  numbers3/
  numbers4/
```

Each `games/<game>/` directory is itself a normal single-game Unified Campaign output with its own prediction locks, protocol artifact, result files, and checksums.

## Scientific boundary

Parallel execution preserves these existing rules:

- chronological development folds;
- Holdout remains excluded from scoring;
- Prospective remains excluded from scoring;
- prediction is durably locked before matching actuals are read;
- every requested catalog model × game receives one result row in completed sub-runs;
- `matrix_complete=true` means matrix coverage, not that every row is `SUCCEEDED`.

Resource identity can differ from a sequential run because each worker receives its effective CPU allocation. This is intentional and prevents a parallel run from pretending to have the same resource budget as a sequential run.

## GPU note

`--device cuda` is not a generic switch that makes core scikit-learn tree estimators use CUDA. GPU-capable libraries must have an explicit device-aware adapter. Current parallelization is therefore useful for CPU-oriented scikit-learn workloads even when an NVIDIA GPU is present.

GPU routing for LightGBM, XGBoost, CatBoost, NeuralForecast, and TSFM should remain explicit and separately runtime-certified rather than silently changing a CPU estimator's implementation identity.
