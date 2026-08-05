# NeuralForecast Database Search-Space Artifact Persistence

## Status

`DB_CAMPAIGN_PERSISTENCE / DRAFT / AUTOMATIC_POLICY_PROMOTION_DISABLED`

This change connects the search-space profile and four-file checksum contract from
PRs #84 and #85 to the database AutoModel campaign. It does not change the selected
sampler, searcher, scheduler, validation objective, model configuration, prediction,
or runtime-certification criteria.

## Stable-module installation

The existing `loto.neuralforecast.db_automodel` module remains the source of its public
classes and functions. Its dataclasses are not copied or moved, so their class identity,
`__module__`, import path, and process-pool serialization contract remain unchanged.

`loto.neuralforecast.__init__` explicitly installs an idempotent facade after importing
the stable module. The facade replaces only these execution entry points:

- `_construct_auto_hint`;
- `_run_single_model`;
- `_worker_entry`;
- `build_campaign_plan`;
- `run_automodel_campaign`.

The original functions are retained on the stable module. A facade reload recovers those
references instead of wrapping an already wrapped function. Model execution uses an
`RLock` and a `ContextVar` while temporarily intercepting planning and construction.
Existing tests or callers that monkeypatch `resolve_auto_model_plan` or
`construct_auto_model` before an execution call remain the delegates invoked by the
interceptors, and the public hooks are restored in `finally`.

## Model-directory contract

Every started database AutoModel writes these files into its existing model directory:

```text
<campaign-output>/models/<model-id>/SEARCH_SPACE_PROFILE.json
<campaign-output>/models/<model-id>/SEARCH_SPACE_PROFILE.sha256
<campaign-output>/models/<model-id>/SEARCH_SPACE_PROFILE_MANIFEST.json
<campaign-output>/models/<model-id>/SEARCH_SPACE_PROFILE_MANIFEST.sha256
```

The files are written and read back before training. A checksum, manifest-entry, schema,
or required-file mismatch fails closed.

## Persistence phases

The model report records one of two phases:

- `planning`: dependency-light evidence available before the model constructor;
- `runtime_resolved`: evidence obtained from the constructed model's resolved config.

For ordinary AutoModels, `AutoModelPlan.search_space_profile` is persisted before
`construct_auto_model`. After construction, an adapter-attached runtime profile is
preferred. If none is attached, the runtime model config is inspected with the planning
profile as an explicit fallback.

The runtime manifest records `planning_profile_sha256`, preserving the relationship
between the pre-constructor contract and the final resolved profile.

## AutoHINT boundary

AutoHINT is Ray-only in the pinned NeuralForecast runtime. Before importing optional Ray
and NeuralForecast dependencies, the campaign persists an honest `UNAVAILABLE` planning
profile explaining that the Ray domains have not yet been resolved. Once the actual
`tune.choice` configuration exists, the facade profiles and persists it before the
`AutoHINT` constructor is called.

If optional imports fail, planning evidence remains available. If the constructor fails,
the runtime-resolved Ray-domain profile remains available.

## Failure durability

`run_report.json` is rewritten after the stable execution function returns or raises. It
embeds:

```text
search_space_evidence.phase
search_space_evidence.profile
search_space_evidence.artifacts
search_space_evidence.artifacts.verification_status
```

A failed constructor, HPO trial, fit, prediction, save/load verification, device check,
or GPU check does not erase already-persisted search-space evidence. Model success and
search-space artifact verification remain independent statuses.

## Campaign aggregation

`campaign_report.json` receives additive fields without changing its existing
`schema_version=1.1.0` contract:

```text
search_space_artifact_status
search_space_verified_model_count
search_space_artifacts.verified_model_count
search_space_artifacts.failed_verification_model_count
search_space_artifacts.missing_evidence_model_count
search_space_artifacts.profiles
```

A failed model with verified profile artifacts still counts as profile-verified. A
process-worker bootstrap failure without model-directory evidence is counted as missing,
not silently treated as verified.

## Dry-run behavior

A dry run does not create per-model artifact files because no model execution starts.
`campaign_plan.json` declares the four required file names, pre-constructor timing,
read-after-write fail-closed verification, and campaign-report aggregation contract.

## Evaluation and leakage boundary

This persistence change is not forecasting-performance evidence. Any Random, TPE,
CMA-ES, Grid, or future scheduler comparison must use identical chronological Train,
Validation and Holdout splits, official search spaces, trial budgets, resource limits,
and multiple seeds. Hit@±1 remains primary, with MAE, MSE, RMSE, position-level and
all-position Hit@±1, mean, variance, worst seed, and required Random, fixed, mean,
median, last-value, frequency, and statistical baselines.

Scaler, encoder, feature selection, and HPO decisions remain Train-only. Holdout and
Prospective outcomes must not alter the search-space profile or search-policy decision.
Prospective predictions remain SHA-256 and timestamp locked before actual values are
known.

## Runtime boundary

Verified search-space files do not certify the model runtime. Formal model success still
requires load, input, inference, output shape, finite predictions and state, device,
GPU PID, VRAM, training-worker evidence, reload inference, prediction equivalence, and
no CPU fallback when GPU execution is required.

## Deferred scope

This change does not automatically promote a model to TPE, CMA-ES, Grid, ASHA, or another
scheduler. It does not perform the all-36 real-runtime campaign, GPU certification,
Holdout comparison, Prospective evaluation, merge, or release.
