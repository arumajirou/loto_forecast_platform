# P15 Model-by-model covariate runtime certification

## Purpose

P15 connects the P14 static capability table to executable evidence. It does not infer
success from a declared model name or a successful import. Each scenario must execute the
protocol-v2 provider, validate the response, inspect persisted artifacts, and preserve a
SHA-256 manifest.

## Profiles

### `smoke`

The six required scenarios cover:

1. TemporalFusionTransformer with native known, past, and static covariates;
2. reload parity for the same TFT artifact;
3. DeepAR with native known and static covariates;
4. Naive with known and static covariates through `covariate_regressor="LR"`;
5. reload parity for the same Naive regressor artifact;
6. DeepAR and TiDE in one explicit multi-model run under the same known/static contract.

### `full`

The full profile derives scenarios from the 29-model P14 inventory. It creates one known
covariate scenario and one static-feature scenario for every model, plus native past-covariate
scenarios for the models that declare native past support. The current matrix contains 60 fit
scenarios. Full execution is intentionally not the default because foundation models may need
network access, model weights, optional dependencies, and substantially more runtime.

## Required evidence

A scenario is `VERIFIED` only when all of the following hold:

- provider process exits successfully;
- response run ID and operation match the request;
- six predictions are returned for three positions and horizon two;
- every prediction mean is finite;
- selected model IDs match exactly;
- P14 capability routes match the expected native or regressor route;
- provider PID is positive and the CPU scenario reports no GPU use;
- provider, execution-plan, timeline, covariate, and capability contexts exist under the
  scenario artifact directory;
- reload scenarios reproduce the fit prediction SHA-256 exactly.

Known runtime provisioning failures are classified as `BLOCKED_RUNTIME`. Unexpected model,
shape, evidence, artifact, or capability errors are classified as `FAILED`. Any `FAILED`
scenario makes the campaign `FAILED`.

## Commands

Smoke profile:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH=src uv run python \
  -m loto.autogluon_campaign.covariate_runtime_certification \
  --repo-root "$PWD" \
  --profile smoke \
  --output-dir "artifacts/autogluon/covariate-runtime-certification/${RUN_ID}"
```

Full model-by-model profile:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH=src uv run python \
  -m loto.autogluon_campaign.covariate_runtime_certification \
  --repo-root "$PWD" \
  --profile full \
  --output-dir "artifacts/autogluon/covariate-runtime-certification-full/${RUN_ID}"
```

The harness executes scenarios sequentially because reload scenarios share fit artifacts and
single-GPU execution must remain isolated. The `--scenario` option can be repeated to shard
independent full-profile fit scenarios across external workers while keeping each output
directory unique.

## Outputs

- `COVARIATE_RUNTIME_CERTIFICATION_REPORT.json`
- `SHA256SUMS`
- per-scenario request, response, stdout, and stderr files
- model artifacts and all P9/P13/P14 context files

## Current verification boundary

The harness and fake-provider regression tests pass locally. AutoGluon 1.5.0 is not installed
in the current execution environment, so no real model is certified by P15 yet. PR #57 must
remain Draft until real smoke and full-profile evidence, Ruff, mypy, full pytest, GitHub CI,
and separate GPU certification are complete.
