# BasicTS isolated provider contract

Status: `PARTIALLY_VERIFIED / LOCAL_P0_VERIFIER_PASS / REAL_BASICTS_RUNTIME_PENDING`

This directory documents the first BasicTS integration increment. It deliberately avoids the
root dependency graph, shared workers, shared catalogs, Holdout, Prospective, GPU, and DDP paths.

## Frozen upstream identity

- repository: `GestaltCogTeam/BasicTS`
- package version: `1.1.0`
- revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`
- isolated lane: Python 3.11

The launcher must export:

```bash
export BASICTS_UPSTREAM_REVISION=c2bb6e31e591167e84459775a21a62e70a5893ce
```

A package version alone is not accepted as revision evidence.

## Supported operations

- `identity`: verify exact version and revision marker.
- `validate_config`: resolve only explicitly allowed serialized imports.
- `dlinear_smoke`: train the upstream DLinear module on CPU, check finite state and predictions,
  save the state dictionary, reload it, and require exact re-prediction equality.

## Security boundary

Serialized configuration references are restricted to:

- `basicts.*`
- `loto.adapters.basicts.*`
- `torch.optim.*`
- `torch.optim.lr_scheduler.*`

Unknown keys and non-allowlisted imports fail closed.

## Data and metric contracts

`GameGeometry` preserves game ID, ordered position columns, legal value range, draw number, and
optional draw date. Input is never silently sorted, deduplicated, filled, or repaired.

Hit@±1 is the primary metric. MAE, MSE, RMSE, position-wise Hit@±1, and all-position Hit@±1 are
retained.

## P0 target-host procedure

Run the following from the repository root on a host that can install Python 3.11 dependencies.
Do not mark the PR successful when dependency resolution, an operation, or checksum verification
fails.

```bash
set -Eeuo pipefail

ENVIRONMENT="environments/basicts-py311"
REVISION="c2bb6e31e591167e84459775a21a62e70a5893ce"

uv lock --project "${ENVIRONMENT}" --python 3.11
uv lock --check --project "${ENVIRONMENT}"
uv sync --frozen --project "${ENVIRONMENT}" --python 3.11

export PYTHONPATH="${PWD}/src"
export BASICTS_UPSTREAM_REVISION="${REVISION}"

uv run --frozen --project "${ENVIRONMENT}" \
  python scripts/run_basicts_provider.py \
  --request configs/basicts_campaign/identity.json

uv run --frozen --project "${ENVIRONMENT}" \
  python scripts/run_basicts_provider.py \
  --request configs/basicts_campaign/validate_config.json

uv run --frozen --project "${ENVIRONMENT}" \
  python scripts/run_basicts_provider.py \
  --request configs/basicts_campaign/dlinear_smoke.json

uv run --frozen --project "${ENVIRONMENT}" \
  python -m loto.basicts_campaign.certification \
  --lockfile "${ENVIRONMENT}/uv.lock" \
  --identity-dir artifacts/basicts/p0/identity \
  --config-dir artifacts/basicts/p0/validate-config \
  --dlinear-dir artifacts/basicts/dlinear-smoke \
  --output-dir artifacts/basicts/p0/certification

(
  cd artifacts/basicts/p0/certification
  sha256sum -c P0_CERTIFICATION_REPORT.json.sha256
)
```

The P0 verifier requires all of the following before it writes a `PASS` report:

- a non-empty `uv.lock` containing the frozen BasicTS revision;
- exact BasicTS version and revision in every provider response;
- portable `SHA256SUMS` verification with no missing, extra, duplicate, or path entries;
- artifact manifest size and SHA-256 agreement;
- real allowlisted config imports;
- DLinear CPU fit and predict with finite state and output;
- save, strict load, and exact re-prediction equality.

The verifier rejects symbolic links and evidence tampering. It writes:

- `P0_CERTIFICATION_REPORT.json`
- `P0_CERTIFICATION_REPORT.json.sha256`

## Local contract verification

The local environment does not contain BasicTS and cannot access the external dependency sources.
The current local result is therefore limited to contract and verifier tests:

- focused tests: `16 passed`;
- optional real BasicTS smoke: `1 skipped`;
- compileall: `PASS`;
- new-file 100-character line audit: `PASS`.

The skipped runtime test is not counted as success.

## Certification boundaries

This increment does not claim:

- successful dependency resolution or a reviewed `uv.lock`;
- real BasicTS 1.1.0 runtime execution;
- launcher, Runner, TensorBoard, distributed, GPU, AMP, or DDP certification;
- baseline/model inventory completeness;
- chronological CV, OOF, HPO, Holdout, or Prospective results;
- accuracy improvement or baseline superiority;
- live MLflow or PostgreSQL persistence;
- shared worker or catalog integration;
- GitHub Actions success.
