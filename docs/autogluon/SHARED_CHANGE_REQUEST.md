# AutoGluon Shared Integration Change Request

Status: `PROPOSED / BLOCKED_SHARED_SCOPE`

## Purpose

Connect the isolated AutoGluon TimeSeries protocol-v2 provider to the production model
worker and shared model catalog without weakening the fail-closed runtime and evidence
contracts implemented by Draft PR #57.

This document is a change request only. It does not authorize or implement edits to
shared files.

## Current certified boundary

The AutoGluon-private implementation currently owns:

- `scripts/run_autogluon_timeseries_provider.py`;
- `src/loto/adapters/autogluon/**`;
- `src/loto/autogluon_campaign/**`;
- `configs/autogluon_campaign/**`;
- `tests/adapters/autogluon/**`;
- `tests/autogluon_campaign/**`;
- `docs/autogluon/**`.

The existing production worker continues to send schema version 1. Protocol version 2
is therefore not yet the default production path.

## Requested shared changes

### 1. `src/loto/models/workers.py`

Add a protocol-v2 request builder and response adapter that:

- derives position columns dynamically instead of assuming seven positions;
- constructs `GameGeometry` from the active game contract;
- maps umbrella preset, explicit single model, explicit multi-model, and bounded HPO
  requests to the protocol-v2 fields;
- sends the selected `model_id` instead of accepting and ignoring it;
- preserves `seed=1` for Auto and search execution;
- verifies provider schema and provider version before consuming a response;
- verifies item IDs, position count, horizon, prediction shape, quantiles, and finite
  values;
- retains request, plan, geometry, timeline, artifact, device, PID, and SHA-256 evidence;
- maps structured provider errors without silently falling back to another model;
- keeps the schema-v1 route available only as an explicitly named compatibility path
  during migration.

### 2. `src/loto/models/catalog_full.py`

Represent AutoGluon capabilities without converting source declaration into runtime
success:

- retain a stable AutoGluon provider entry;
- expose source-declared, runtime-discovered, runtime-importable, and
  runtime-certified states separately;
- do not mark all 29 source models as executable from a static catalog alone;
- use the generated runtime inventory as evidence for model availability;
- keep models with missing optional dependencies visible but non-certified;
- preserve the nine selectable ensemble names and eight unique ensemble classes,
  including `PerformanceWeighted` and the `Weighted -> Greedy` alias.

A generated or runtime-backed extension is preferred over manually duplicating 29 model
rows in the shared catalog.

### 3. Shared tests

Add focused tests that prove:

- Numbers3, Numbers4, Mini Loto, Loto6, and Loto7 requests preserve their geometry;
- `model_id` changes the effective AutoGluon hyperparameter keys;
- preset and explicit-model modes cannot be mixed silently;
- position and horizon mismatches fail closed;
- quantile and finite-value failures are rejected;
- save/load uses the same model artifact and protocol context;
- CPU fallback is recorded and is never relabeled as GPU certification;
- unavailable optional dependencies do not become runtime success;
- the legacy schema-v1 path remains explicit and removable.

## Concurrency contract

The shared integration must retain the campaign limits:

- outer campaign workers: `8`;
- maximum concurrent AutoGluon jobs: `2`;
- maximum concurrent GPU AutoGluon jobs: `1`;
- nested AutoGluon execution must not create uncontrolled outer parallelism.

These values must be persisted in run evidence rather than inferred from defaults.

## Preconditions for implementation

All of the following are required before shared-file edits begin:

1. Draft PR #57 remains mergeable and its owned-path scope audit passes.
2. The real AutoGluon 1.5.0 P5 certification executes successfully for Naive, Theta,
   preset, multi-model, bounded HPO, save/load, and forced CPU fallback.
3. `RUNTIME_CERTIFICATION_REPORT.json` and `SHA256SUMS` verify successfully.
4. Issue #58 is resolved enough for a GitHub Actions job to reach workflow step
   creation and produce accessible logs.
5. Ruff, mypy, focused tests, compileall, and one full pytest run complete.
6. GPU certification remains a separate gate and is not inferred from CUDA
   availability.

Until these preconditions pass, the shared integration status remains
`BLOCKED_SHARED_SCOPE`.

## Proposed delivery shape

Use a separate stacked Draft PR after the private provider is runtime-certified:

- base: the certified AutoGluon provider branch or its merged commit;
- head: a dedicated shared-integration branch;
- changed shared files limited to the approved worker, catalog, and focused tests;
- no root dependency or workflow edits unless separately justified;
- no automatic merge.

## Acceptance criteria

The shared integration may be marked `VERIFIED` only when:

- a real production worker request reaches protocol v2;
- the requested model identity is visible in the effective execution plan;
- load, input, inference, output shape, finite values, device, PID, artifact, and hashes
  are verified;
- CPU fallback is explicit;
- GPU success includes positive process and VRAM evidence;
- no game geometry is hardcoded to seven positions;
- schema-v1 compatibility is explicit and covered by tests;
- repository CI produces a complete result with accessible logs.

## Rollback

Before merge, close the stacked Draft PR. After merge, revert the shared-integration
commit normally. Do not rewrite `main`, force-push shared history, or remove protocol-v2
evidence artifacts.
