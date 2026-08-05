# NeuralForecast downstream lineage integrity

## Purpose

A promotion decision is not sufficient by itself to prove that a later run used
the same configuration, code, data contract, coverage evidence, runtime evidence,
or chronological predecessor that was reviewed earlier.

This layer freezes those inputs in `LINEAGE.json` and makes the standard
`loto-auto-campaign verify` command recompute them. A modified source run,
predecessor run, campaign configuration, data contract, promotion gate, coverage
run, or runtime campaign makes verification fail even when its local
`SHA256SUMS` was regenerated after the modification.

## Source run and predecessor run are different

`--source-run` remains the run from which selected model configurations and the
promotion plan are loaded. For Holdout and Prospective this remains the verified
`validate-trials` run.

`--predecessor-run` records chronological progression:

| Target stage | Required source stage | Required predecessor stage |
|---|---|---|
| `hpo` | none | none |
| `validate-trials` | `hpo` | same as source |
| `oof` | `validate-trials` | same as source |
| `holdout` | `validate-trials` | `oof` |
| `prospective` | `validate-trials` | `holdout` |

This separation avoids changing the existing selected-config loading contract
while preventing Holdout or Prospective execution from skipping the immediately
preceding evaluation stage.

## Required execution sequence

### 1. HPO

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  run \
  --stage hpo \
  --coverage-run artifacts/api-coverage/<verified-run> \
  --runtime-run artifacts/neuralforecast-db/<runtime-run> \
  --output artifacts/hpo/<run>

uv run loto-auto-campaign verify --run artifacts/hpo/<run>
```

The runtime argument is required only when the campaign configuration requests
GPU resources.

### 2. Validation replay

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  run \
  --stage validate-trials \
  --source-run artifacts/hpo/<verified-run> \
  --coverage-run artifacts/api-coverage/<verified-run> \
  --runtime-run artifacts/neuralforecast-db/<runtime-run> \
  --output artifacts/validate-trials/<run>

uv run loto-auto-campaign verify --run artifacts/validate-trials/<run>
```

### 3. OOF

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  run \
  --stage oof \
  --source-run artifacts/validate-trials/<verified-run> \
  --coverage-run artifacts/api-coverage/<verified-run> \
  --runtime-run artifacts/neuralforecast-db/<runtime-run> \
  --output artifacts/oof/<run>

uv run loto-auto-campaign verify --run artifacts/oof/<run>
```

### 4. Holdout

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  run \
  --stage holdout \
  --source-run artifacts/validate-trials/<verified-run> \
  --predecessor-run artifacts/oof/<verified-run> \
  --coverage-run artifacts/api-coverage/<verified-run> \
  --runtime-run artifacts/neuralforecast-db/<runtime-run> \
  --output artifacts/holdout/<run>

uv run loto-auto-campaign verify --run artifacts/holdout/<run>
```

### 5. Prospective

```bash
uv run loto-auto-campaign \
  --config configs/auto_campaign/campaign.yaml \
  run \
  --stage prospective \
  --source-run artifacts/validate-trials/<verified-run> \
  --predecessor-run artifacts/holdout/<verified-run> \
  --coverage-run artifacts/api-coverage/<verified-run> \
  --runtime-run artifacts/neuralforecast-db/<runtime-run> \
  --output artifacts/prospective/<run>

uv run loto-auto-campaign verify --run artifacts/prospective/<run>
```

## Pre-execution checks

Before a gated runner starts, the lineage pipeline requires:

- the expected source and predecessor stages;
- `manifest.json` status `PASS` for each input run;
- `lineage_status=PASS` for each gated input run;
- a matching `LINEAGE.json` hash;
- valid complete root `SHA256SUMS`;
- `VERIFICATION_REPORT.json` status `PASS`;
- the PR #50 promotion gate to pass.

A failure writes `<requested-output>.PROMOTION_GATE_BLOCKED.json`, does not create
the requested run directory, and exits with code 2 through the existing CLI
contract.

## LINEAGE.json

A successful gated run records:

- target stage and UTC creation time;
- SHA-256 of `campaign_config.json`;
- SHA-256 of `data_contract.json`;
- SHA-256 of `PROMOTION_GATE.json`;
- run manifest `code_sha256` and `data_sha256`;
- source-run manifest, `SHA256SUMS`, code, data, and lineage evidence;
- chronological predecessor evidence;
- verified API coverage evidence;
- runtime campaign report evidence when supplied;
- a canonical `chain_sha256` over the complete evidence payload.

The root manifest adds:

```text
lineage_schema_version=all-auto-lineage-v1
lineage_status=PASS
lineage_path=LINEAGE.json
lineage_sha256=<sha256>
lineage_chain_sha256=<canonical-chain-sha256>
```

The root `SHA256SUMS` is regenerated after the lineage and manifest are written.

## Standard verification

```bash
uv run loto-auto-campaign verify --run artifacts/<stage>/<run>
```

The report now includes:

```text
promotion_gate_verification
lineage_verification
```

For gated stages, missing lineage is a failure rather than `NOT_APPLICABLE`.
Verification checks the current contents of every recorded external run. Changing
an external manifest and regenerating that external run's own `SHA256SUMS` still
fails because the downstream lineage retained the previous manifest and
`SHA256SUMS` digests.

## Fail-closed boundaries

- A non-PASS stage result does not receive a PASS lineage.
- Holdout cannot run without a verified OOF predecessor.
- Prospective cannot run without a verified Holdout predecessor.
- CPU API coverage cannot replace GPU runtime evidence.
- Best-model-only or best-seed-only runtime evidence remains insufficient.
- Holdout and Prospective metrics are not used to modify earlier model selection.

## Portability boundary

The first schema records resolved absolute evidence paths. Moving only one run
without its dependency tree causes verification to fail. Export tooling must copy
the complete referenced tree or produce a later portable path-rebinding manifest;
no path rebinding is silently performed by this implementation.
