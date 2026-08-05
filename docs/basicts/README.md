# BasicTS isolated provider contract

Status: `PARTIALLY_VERIFIED / REAL_BASICTS_RUNTIME_PENDING`

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

## Runtime example

```bash
uv run --project environments/basicts-py311 \
  python scripts/run_basicts_provider.py \
  --request configs/basicts_campaign/dlinear_smoke.json
```

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
