# NeuralForecast downstream lineage integrity

## Purpose

A promotion decision alone does not prove that a later run used the same
configuration, data contract, code identity, API coverage evidence, runtime
evidence, or chronological predecessor that was previously reviewed.

This layer adds two complementary records:

- `LINEAGE.json` fixes the dependency chain used by a gated run;
- `VERIFICATION_SEAL.json` binds a successful verification result to the exact
  immutable contents of that run.

The standard `loto-auto-campaign verify` command recomputes both contracts. A
changed dependency, changed run file, stale PASS report, incorrect stage order,
or missing seal produces `FAIL` even if a local `SHA256SUMS` was regenerated
after the change.

## Source run and predecessor run are different

`--source-run` supplies selected model configurations and the promotion plan.
For Holdout and Prospective this remains the verified `validate-trials` run.

`--predecessor-run` proves chronological progression:

| Target stage | Required source stage | Required predecessor stage |
|---|---|---|
| `hpo` | none | none |
| `validate-trials` | `hpo` | same HPO run |
| `oof` | `validate-trials` | same validation run |
| `holdout` | `validate-trials` | `oof` |
| `prospective` | `validate-trials` | `holdout` |

This preserves the existing selected-config loading contract while preventing a
Holdout or Prospective run from skipping an immediately preceding evaluation
stage.

## Evidence preparation

Before HPO or any later stage, run standard verification on the API coverage run
using the code from this branch. A PASS verification creates its verification
seal.

```bash
uv run loto-auto-campaign verify \
  --run artifacts/api-coverage/<run>
```

Every HPO, validation, OOF, Holdout, and Prospective run must also be verified
before it can be used by the next stage.

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

`--runtime-run` is required only when the campaign configuration requests GPU
resources.

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

Before a gated runner starts, the combined promotion-lineage pipeline requires:

- PR #50 promotion gate status `PASS`;
- the expected source and predecessor stages;
- input `manifest.json` status `PASS`;
- `lineage_status=PASS` for gated input runs;
- a matching `LINEAGE.json` hash;
- valid complete root `SHA256SUMS`;
- `VERIFICATION_REPORT.json` status `PASS`;
- a current `VERIFICATION_SEAL.json` whose content fingerprint still matches;
- a verified and currently sealed API coverage run.

A failure writes:

```text
<requested-output>.PROMOTION_GATE_BLOCKED.json
```

The requested run directory is not created and the existing non-PASS CLI
contract exits with code 2.

## LINEAGE.json

A successful gated run records:

- target stage and UTC creation time;
- SHA-256 of `campaign_config.json`;
- SHA-256 of `data_contract.json`;
- SHA-256 of `PROMOTION_GATE.json`;
- run manifest `code_sha256` and `data_sha256`;
- source-run manifest, SHA list, code, data, and lineage evidence;
- chronological predecessor evidence;
- verified API coverage evidence;
- runtime campaign report evidence when supplied;
- canonical `chain_sha256` over the complete evidence payload.

The root manifest adds:

```text
lineage_schema_version=all-auto-lineage-v1
lineage_status=PASS
lineage_path=LINEAGE.json
lineage_sha256=<sha256>
lineage_chain_sha256=<canonical-chain-sha256>
```

The root `SHA256SUMS` is regenerated after the lineage and manifest are written.

## Stage-semantic verification

Hash equality is not treated as sufficient. Standard verification separately
checks the meaning of the chain:

- HPO must not have source or predecessor evidence;
- validation and OOF source/predecessor paths must be the same required run;
- Holdout must use validation as config source and OOF as predecessor;
- Prospective must use validation as config source and Holdout as predecessor;
- source and predecessor verification states must be `PASS`;
- a GPU promotion must retain PASS runtime evidence;
- run code and data SHA-256 values must be present.

A syntactically valid, self-consistent lineage that encodes the wrong stage order
therefore fails.

## VERIFICATION_SEAL.json

A PASS standard verification creates a deterministic seal with:

```text
schema_version=all-auto-verification-seal-v1
contract_version=promotion-lineage-verifier-v1
status=PASS
sealed_at=<first successful seal time>
content_sha256=<path-and-content fingerprint>
content_file_count=<immutable file count>
manifest_sha256=<sha256>
promotion_gate_sha256=<sha256 or null>
lineage_sha256=<sha256 or null>
components=<verification status summary>
```

The fingerprint includes every run file except these mutable verification outputs
at the root:

```text
SHA256SUMS
VERIFICATION_REPORT.json
VERIFICATION_SEAL.json
```

Path names and file bytes are framed into the digest, so adding, deleting,
renaming, or modifying an immutable file changes the seal. Nested SHA lists and
nested evidence files remain part of the fingerprint.

Re-verifying unchanged content preserves the original `sealed_at` and the same
seal file hash. If an existing seal no longer matches, standard verification
fails and preserves that old seal as audit evidence; it does not silently replace
it with a new PASS seal.

## Standard verification report

```bash
uv run loto-auto-campaign verify --run artifacts/<stage>/<run>
```

`VERIFICATION_REPORT.json` includes:

```text
coverage_state_verification
promotion_gate_verification
lineage_verification
preexisting_verification_seal
verification_seal
```

For gated stages, missing lineage is a failure rather than `NOT_APPLICABLE`.
Changing an external source or predecessor manifest and regenerating that
external run's own `SHA256SUMS` still fails because the downstream lineage
retains the previous manifest and SHA-list digests. Changing an input run after
it was verified also invalidates its verification seal before a later stage can
start.

## Fail-closed boundaries

- A non-PASS stage result does not receive a PASS lineage.
- Holdout cannot run without a verified and sealed OOF predecessor.
- Prospective cannot run without a verified and sealed Holdout predecessor.
- A stale PASS verification report is insufficient without a matching seal.
- CPU API coverage cannot replace GPU runtime evidence.
- Best-model-only or best-seed-only runtime evidence remains insufficient.
- Holdout and Prospective metrics are not used to modify earlier selection.

## Trust and portability boundaries

The first lineage schema records resolved absolute evidence paths. Moving only
one run without its dependency tree causes verification to fail. Portable path
rebinding is not implemented.

The seal detects accidental or unapproved local mutation relative to the retained
seal and downstream lineage records. It is not a digital signature, external
timestamp, or remote transparency log. An authorized operator who deletes every
local record and constructs a new evidence tree is outside this implementation's
authenticity guarantees. No stronger external-authenticity claim is made.
