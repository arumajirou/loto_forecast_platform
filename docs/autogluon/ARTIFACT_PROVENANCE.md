# AutoGluon Artifact Provenance

Status: IMPLEMENTED_P9 / locally verified / real AutoGluon execution pending

## Problem corrected

The initial protocol-v2 load path accepted any non-empty predictor directory and rewrote
`loto_provider_context_v2.json`, `loto_execution_plan_v2.json`, and
`loto_timeline_mapping_v2.json` after loading. That behavior could erase the original fit
provenance and did not prove that the requested model, geometry, predictor contract, or
AutoGluon version matched the saved artifact.

## Fit-time seal

A successful fit now records:

- canonical request SHA-256;
- execution plan and validated `plan_sha256`;
- source-order and complete timeline-mapping SHA-256 values;
- geometry SHA-256;
- exact `autogluon.timeseries==1.5.0` identity;
- observed model names and best model;
- requested-to-observed model-identity evidence.

The provider refuses to return `OK` when the observed model names do not contain every
explicitly selected model identity. HPO and refit suffixes remain recognizable without
accepting unrelated model names.

## Load-time gate

Before `TimeSeriesPredictor.load()` can invoke its pickle-backed loader, the provider
requires and validates all three original context files. It rejects:

- missing or invalid context JSON;
- embedded and standalone execution-plan differences;
- invalid or mismatched plan hashes;
- embedded and standalone timeline differences;
- source-order or timeline hash mismatches;
- geometry mismatch;
- execution-mode or requested-model mismatch;
- predictor target, horizon, frequency, or quantile mismatch;
- library-version mismatch;
- unverified saved model identity.

Only after these checks pass may the trusted predictor artifact be loaded. The loaded
predictor's model names must also match the saved runtime snapshot.

## Immutability

`load_predict` no longer rewrites fit-time context. It returns references to the original
provider context, execution plan, and timeline mapping. The response records a canonical
`saved_context_sha256`, so the caller and runtime-certification harness can prove that the
same fit context was used for reload.

## Prediction seed

The provider now passes the request seed explicitly to
`TimeSeriesPredictor.predict(..., random_seed=seed)`. The response records
`prediction_random_seed`; the project default remains `seed=1`.

## Device evidence boundary

CUDA availability alone no longer sets `resolved_device=cuda`. CPU requests and an
unavailable-CUDA fallback can be resolved to CPU. CUDA-capable runs remain `unknown` until
later process and VRAM evidence proves actual GPU execution.

## Verification completed

- focused provenance and provider tests: 21 passed;
- Python compileall: PASS;
- 100-character line policy: PASS;
- real AutoGluon 1.5.0 runtime: execution pending;
- GitHub Actions: blocked before workflow-step creation under Issue #58.
