# BasicTS provider contract v1

## Status

`IMPLEMENTED / LOCAL_CONTRACT_VERIFICATION_REQUIRED / REAL_BASICTS_RUNTIME_PENDING`

## Frozen provenance

- project base: `main` at `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- BasicTS package: `1.1.0`
- upstream revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`
- isolated lane: Python 3.10, CPU only

## Scope

The first increment introduces only BasicTS-owned paths. It does not modify the root dependency
lock, common workers, common model catalogs, root CLI, GitHub Actions, or top-level README.

## Operations

- `identity`: verify installed distribution and module versions.
- `validate_config`: reject unknown keys, GPU requests, automatic test evaluation, and unsafe
  dynamic imports.
- `compile_dataset`: validate immutable chronological draw data and materialize Train and
  Validation arrays. Formal Holdout values are not written into the BasicTS dataset directory.
- `construct_forward_save_load_smoke`: construct a BasicTS forecasting config, execute one
  deterministic CPU forward pass with a project-owned model, save/load state, and compare output.

The smoke operation deliberately does not claim training, validation, or forecasting accuracy.

## Security boundary

Declarative imports are restricted to:

- `basicts.*`
- `loto.adapters.basicts.*`
- `torch.optim.*`
- `torch.optim.lr_scheduler.*`

Private identifiers, parent traversal, unknown schema fields, and unsupported operations fail closed.

## Evaluation contract

Hit@±1 is primary. MAE, MSE, RMSE, position-wise Hit@±1, and all-position Hit@±1 are retained.
Deterministic random, fixed, mean, median, last, frequency, and seasonal-naive baselines are
provided. Formal model comparison must use chronological Train/Validation/Holdout/Prospective
stages and multiple seeds; this first increment does not run that campaign.

## Evidence

Each provider request writes atomic JSON evidence, `ARTIFACT_MANIFEST.json`, and portable
`SHA256SUMS`. BasicTS's MD5 configuration identifier is retained only as an upstream compatibility
field; SHA-256 is the evidence hash.

## Certification boundaries

Not certified by this increment:

- dependency resolution or a reviewed isolated `uv.lock`;
- BasicTS package import on the target host;
- BasicTS runner training or evaluation;
- upstream baseline/config inventory;
- real dataset accuracy;
- Holdout or Prospective results;
- GPU, DDP, AMP, PID, VRAM, or CPU-fallback evidence;
- MLflow or PostgreSQL persistence;
- shared worker/catalog integration;
- GitHub Actions success.
