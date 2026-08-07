# NeuralForecast downstream promotion gate

## Purpose

A successful API call, constructor probe, model fit, or first prediction is not enough to
start formal HPO, OOF, Holdout, or Prospective execution. The promotion gate combines two
independent evidence sources and fails closed before expensive downstream work starts.

1. **API contract evidence** — an integrated and verified `api-coverage` run.
2. **Runtime evidence** — a complete 36-model database AutoModel campaign when GPU
   resources are requested.

CPU-only API evidence can authorize a CPU campaign. It cannot be reused or relabeled as
GPU runtime success.

## Gated stages

The following stages require `--coverage-run`:

```text
hpo
validate-trials
oof
holdout
prospective
```

`smoke`, `coverage`, and `api-coverage` remain ungated because they create evidence rather
than consume it.

## CPU example

The campaign configuration must request CPU resources (`accelerator=cpu` and
`gpus_per_trial=0`).

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign-cpu.yaml \
  run \
  --stage hpo \
  --coverage-run artifacts/api-coverage/<verified-run> \
  --output artifacts/hpo/<run>
```

The coverage run must contain a valid root `SHA256SUMS`, `manifest.json`, and
`VERIFICATION_REPORT.json`. The root and nested coverage states must both be `VERIFIED`,
and `coverage_state_verification.status` must be `PASS`.

## GPU example

A GPU campaign additionally requires a database AutoModel runtime campaign containing all
36 registered AutoModels.

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  run \
  --stage hpo \
  --coverage-run artifacts/api-coverage/<verified-run> \
  --runtime-run artifacts/neuralforecast-db/<runtime-run> \
  --output artifacts/hpo/<run>
```

`--runtime-run` may point to either the runtime directory or its
`campaign_report.json` file.

## GPU runtime requirements

The campaign report must prove all of the following for exactly 36 unique models:

- campaign `status=SUCCEEDED`;
- campaign `certification_status=RUNTIME_CERTIFIED`;
- 36 started, 36 succeeded, 36 runtime-certified, and 0 failed models;
- every model report is `SUCCEEDED` and `RUNTIME_CERTIFIED`;
- runtime certification `status=PASS`;
- GPU execution was explicitly required;
- formal training-worker CUDA evidence exists;
- pre-save inference used CUDA;
- reload inference used CUDA;
- pre-save and reload device fields identify CUDA;
- pre-save and reload CUDA memory evidence is positive;
- pre-save and reload `nvidia-smi` PID evidence is verified;
- save/load completed;
- inference completed;
- prediction shape and `(unique_id, ds)` identity match;
- predictions and state dictionaries are finite;
- deterministic values or seeded stochastic distributions match;
- `cpu_fallback=false`.

One failing or incomplete model blocks the entire GPU promotion decision. Best-model-only
or best-seed-only success is not accepted.

## Blocked execution

A blocked stage is not started. The CLI returns status `BLOCKED`, exits with code 2, and
writes a sibling evidence file:

```text
<requested-output>.PROMOTION_GATE_BLOCKED.json
```

The file contains all failed requirements and the normalized coverage/runtime evidence
summaries. The requested run directory is not created by the gate.

## Passed execution

After the existing stage runner completes, the run directory receives:

```text
PROMOTION_GATE.json
```

The run `manifest.json` is extended with:

```text
promotion_gate_status=PASS
promotion_gate_path=PROMOTION_GATE.json
promotion_gate=<embedded decision>
```

The root `SHA256SUMS` is regenerated after these fields and artifacts are written.

## Certification boundaries

The gate does not claim that the current local RTX environment has been executed. While
local runtime is unavailable, GPU stages remain blocked because no valid runtime campaign
can satisfy the GPU evidence contract.

The gate also does not evaluate accuracy or choose a champion. Hit@±1, MAE, MSE, RMSE,
position-wise metrics, all-position Hit@±1, multiple seeds, Holdout, and Prospective
promotion remain separate downstream decisions.
