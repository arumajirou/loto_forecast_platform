# NeuralForecast Database Runtime Verification

## Status

`RUNTIME_VERIFIER_IMPLEMENTED / REAL_GPU_EXECUTION_PENDING / DRAFT`

This change adds a fail-closed verifier and execution wrapper for the database-backed
NeuralForecast AutoModel campaign stacked on PR #88. It does not claim that the real
NeuralForecast 3.2.0 campaign or the registered RTX 5070 Ti has passed.

## Purpose

A completed training command, a saved model directory, or a `runtime_certification.json`
file is not sufficient by itself. The verifier checks the complete relationship between:

- `campaign_plan.json`;
- `campaign_report.json`;
- every model `run_report.json`;
- every model `runtime_certification.json`;
- the four search-space profile artifacts;
- prediction artifacts before and after reload;
- seeded sample artifacts for stochastic models;
- campaign and model counts;
- GPU training, inference, device, VRAM, PID, and CPU-fallback evidence when GPU is
  required.

## Commands

### CPU smoke

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
LOTO_NO_WAIT=1 \
./scripts/run_numbers4_nf_runtime_verification.sh cpu-smoke \
  /absolute/path/to/datasets.sqlite3
```

This runs the existing two-model smoke campaign with `gpus=0` and verifies save, load,
inference, shape, key identity, finite values, prediction equivalence, state dictionaries,
and search-space artifacts. It does not require CUDA evidence and cannot certify GPU
execution.

### GPU smoke

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
LOTO_NO_WAIT=1 \
./scripts/run_numbers4_nf_runtime_verification.sh gpu-smoke \
  /absolute/path/to/datasets.sqlite3
```

The wrapper fixes `seed=1`, requests one GPU per model, retains bounded outer concurrency,
and requires both smoke models to pass formal GPU certification.

### GPU full campaign

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
LOTO_NO_WAIT=1 \
LOTO_NUM_SAMPLES=10 \
LOTO_WORKERS=8 \
LOTO_MAX_GPU_JOBS=1 \
./scripts/run_numbers4_nf_runtime_verification.sh gpu-full \
  /absolute/path/to/datasets.sqlite3
```

The full mode requires exactly 36 unique model reports and all 36 models to be runtime
certified. One missing model, one CPU fallback, one failed profile checksum, or one
incomplete GPU evidence record fails the complete verification.

### Verify an existing run

```bash
uv run python scripts/verify_neuralforecast_db_runtime.py \
  runs/<database-campaign-run> \
  --expected-model-count 2 \
  --require-gpu
```

Use `--require-cpu` for a CPU-only run. Omitting both flags derives the requirement from
`campaign_plan.json`.

## Always-required runtime checks

Every model must prove:

- model status `SUCCEEDED`;
- certification status `RUNTIME_CERTIFIED`;
- runtime certification status `PASS`;
- save/load completed;
- inference after reload completed;
- output shape matched;
- `(unique_id, ds)` identities matched;
- predictions were finite;
- fitted and reloaded state dictionaries were finite;
- deterministic values or seeded stochastic distributions matched;
- `failed_checks` was empty;
- `cpu_fallback` was false;
- predictions before and after reload existed;
- stochastic sample files existed when the runtime policy was stochastic;
- all four search-space profile artifacts passed read-after-write checksum and manifest
  verification.

## Additional GPU checks

When GPU is required, each model must additionally prove:

- the campaign plan required GPU execution;
- `require_gpu=true` in runtime evidence;
- non-empty training-worker evidence;
- `formal_cuda_training_evidence=true`;
- pre-save inference CUDA evidence;
- reload inference CUDA evidence;
- combined CUDA execution evidence;
- CUDA parameter or trainer device in both inference phases;
- positive allocated, reserved, or peak CUDA memory in both phases;
- verified `nvidia-smi` process evidence in both phases;
- no CPU fallback.

A driver snapshot after training is not accepted as training-worker proof.

## Verification artifacts

The verifier writes these additive files into the campaign run directory:

```text
VERIFICATION_REPORT.json
VERIFICATION_SUMMARY.txt
RUNTIME_VERIFICATION_ENVIRONMENT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

`RUNTIME_VERIFICATION_ENVIRONMENT.json` records the verifier host, installed package
versions, Git state, `uv`, and current `nvidia-smi` output. This is environmental context,
not a substitute for the per-model execution evidence captured during training and
inference.

`ARTIFACT_MANIFEST.json` inventories only critical audit artifacts. It deliberately does
not hash every byte of large retained model bundles. `SHA256SUMS` covers the critical
campaign, model, verifier, summary, environment, and manifest files. A later modification
of any covered artifact is detected.

## Exit status

- exit `0`: all required checks passed;
- exit `2`: structured verification completed with one or more failed checks;
- another non-zero exit: execution or verifier infrastructure failed before a complete
  decision could be written.

## Accuracy and leakage boundary

Runtime verification does not demonstrate forecasting accuracy. Formal model comparison
must still use chronological Train, Validation, Holdout, and Prospective boundaries.
Scaler, encoder, feature selection, and HPO decisions remain Train-only. Prospective
predictions remain SHA-256 and timestamp locked before actual values are known.

Hit@±1 remains the primary metric, accompanied by MAE, MSE, RMSE, position-level and
all-position Hit@±1, multiple-seed mean, variance, worst seed, and Random, fixed, mean,
median, last-value, frequency, and statistical baselines.

## Deferred scope

This change does not:

- execute the real target-host smoke inside GitHub Actions;
- certify the RTX 5070 Ti;
- run all 36 models in the current connector environment;
- activate automatic TPE, CMA-ES, Grid, ASHA, or another policy;
- select a champion;
- evaluate Holdout or Prospective accuracy;
- merge or release the stacked PRs.
