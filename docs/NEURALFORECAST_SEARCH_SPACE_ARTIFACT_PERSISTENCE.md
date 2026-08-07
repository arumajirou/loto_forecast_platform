# NeuralForecast Search-Space Artifact Persistence

## Status

`AUTO_CAMPAIGN_PERSISTENCE / DRAFT / DB_CAMPAIGN_PENDING`

This change persists the search-space evidence introduced by the planning-profile
foundation before an AutoModel constructor or training call can fail. It does not
change the selected sampler, scheduler, validation loss, or forecasting output.

## Durable location

Each auto-campaign task writes to a task-key-specific directory:

```text
<run-root>/search_space_profiles/<task-key>/
```

The directory is separate from `trial_work`, which is deleted after a successful
task, and from `tasks/<task-key>`, whose early creation would prevent the runner's
existing retry and collision checks from working correctly. Evidence therefore
survives constructor, dependency, HPO, training, or runtime-certification failure
without making a failed task look complete.

## Files

Each evidence directory contains:

- `SEARCH_SPACE_PROFILE.json`
- `SEARCH_SPACE_PROFILE.sha256`
- `SEARCH_SPACE_PROFILE_MANIFEST.json`
- `SEARCH_SPACE_PROFILE_MANIFEST.sha256`

The dedicated manifest records the profile contract hash, the exact serialized-file
hash, context such as model/backend/seed/trial budget, and hashes of the profile and
checksum files. Persistence verifies all four files before returning.

## Timing

The profile and manifest are written after the official/fixed search configuration is
resolved but before search-algorithm materialization and before the AutoModel
constructor. This preserves evidence even when Ray, Optuna, NeuralForecast, the model
constructor, or later training fails.

## Profile selection

- fixed config and smoke config: `profile_fixed_config`
- formal Ray search dict: `profile_ray_config`
- formal Optuna define-by-run callable: `profile_optuna_config`
- AutoHINT: fixed profile for smoke/fixed runs, Ray-domain profile for formal HPO

Optuna callable evidence remains `PARTIAL`; finite recording-trial probes do not prove
that every possible conditional branch was observed.

## Constructor evidence

The existing constructor artifact remains backward compatible and now optionally
contains:

```text
search_space_profile
search_space_artifacts
```

The model object receives the same profile and artifact metadata. Existing callers
that use `_artifact_kwargs(effective, ledger)` without a search-policy object remain
supported.

## Evaluation and leakage boundary

This persistence change does not claim accuracy improvement. Random-versus-TPE or
other comparisons must retain identical chronological Train, Validation and Holdout
splits, official search spaces, trial budgets, resource limits, and multiple seeds.
Hit@±1 remains primary, with MAE, MSE, RMSE, position/all-position Hit@±1, mean,
variance, worst seed, and required baselines.

Scaler, encoder, feature selection and HPO decisions remain Train-only. Holdout and
Prospective outcomes must not alter the profile or sampler decision. Prospective
predictions remain SHA-256 and timestamp locked before actual values are known.

## Runtime boundary

Persisted search-space evidence is not runtime certification. Formal success still
requires load, input, inference, output shape, finite values, device, GPU PID, VRAM,
training-worker evidence, reload inference, and no CPU fallback when GPU execution is
required.

## Deferred scope

The database AutoModel campaign does not use `auto_campaign/model_factory.py`; its
model-directory hook is intentionally deferred to the next stacked PR. Automatic
sampler promotion and schedulers such as ASHA remain separate evidence-gated changes.
