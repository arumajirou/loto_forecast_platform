# Repository Status

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:46+09:00
repository: arumajirou/loto_forecast_platform
source_of_truth: live GitHub state + code/config at audited main SHA
base_main_sha: 83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f
superseded_by: NONE
```

This file is the current repository-status entry point. It records a point-in-time audit; live GitHub state takes precedence after the `as_of` time.

## Executive status

- Default branch: `main`.
- Audited main: `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f`.
- Unified all-model × all-game development evaluation is merged and callable through `uv run loto3 campaign`.
- Hit@±1-aware select-game decoding now has an explicit `WITHIN_TAU` constrained objective, merged in PR #249 while preserving the historical MAP compatibility API.
- The broad generated catalog remains a 174-entry inventory at this audit boundary; registration is not equivalent to shared routing, runtime certification, OOF completion, or promotion.
- Holdout: **CLOSED / NOT EVALUATED by the unified campaign or decoder change**.
- Prospective: **CLOSED / NOT EVALUATED**.
- Champion/promotion: **NONE AUTHORIZED by this documentation update**.
- Formal Timer Base 84M OOF work remains open in GitHub Issue #239.
- Timer-S1 PR-B immutable runtime/certification work remains open in GitHub Issue #118.

## Merge batch on 2026-08-10

| PR | Result | Main commit | Evidence boundary |
|---|---|---|---|
| #248 | MERGED | `aae45ba9294499f51cc5f1564de1c6ccf5814230` | exact pre-merge head passed Linux full CI and native Windows portability; unified campaign added |
| #244 | MERGED | `c12ca27048d25cdc869fa3cbbfa6e31c727eb529` | actions/checkout v7 workflow update; Linux and Windows exact-head checks passed |
| #242 | MERGED | `cc7ec5473730cfb18100bdfbb5228cf65e571b32` | Ray Tune updated to `>=2.56.1`; latest rebased head passed Linux and native Windows verification |
| #243 | MERGED | `b04f3e40baa1861a5b83da047bdef2655905bd52` | FastAPI updated to `>=0.141.1,<0.142`; exact-head Linux and Windows checks passed |
| #249 | MERGED | `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f` | Hit@±1/within-tau constrained decoder objective; Linux exact-head CI passed; no Holdout/Prospective/model/dependency changes |

GitHub Issue #247 was closed as completed after PR #248 merged.

## Open pull requests at the audit boundary

One PR remained open when this snapshot was prepared:

| PR | Scope | State at audit boundary | Merge decision |
|---|---|---|---|
| #241 | uvicorn / MLflow / Hypothesis / Ruff / GluonTS grouped dependency update | rebased onto current main with head `e5da936410a719bf378302cedb34b8addbbbb2a1`; Linux exact-head full CI running/pending completion and native Windows exact-head queued | `VERIFICATION_PENDING`, not force-merged |

`mergeable=true` alone is not treated as a sufficient merge gate. Current-base identity, exact-head CI and unresolved review state are checked before merge.

## Current direct dependency boundary

At audited main `83f72d2...`:

- `ray[tune]>=2.56.1` is merged in the `full` extra.
- FastAPI is `>=0.141.1,<0.142` in the relevant API/dev/full lanes.
- #241's grouped updates are **not** part of audited main until that PR is merged.
- `uv.lock` is the committed dependency lock and must remain consistent with `pyproject.toml`.

Do not infer a newer dependency state from an open Dependabot branch.

## Unified evaluation campaign

PR #248 introduced the canonical development-only campaign:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Plan-only inventory:

```bash
uv run loto3 campaign --output unused --plan-only
```

Canonical games:

```text
mini
loto6
loto7
bingo5
numbers3
numbers4
```

The campaign materializes every requested broad-catalog model × game pair exactly once. It does **not** hide unsupported combinations. Terminal states include successful and fail-visible states such as `FAILED`, `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `PARTIAL_SEEDS`, and `NON_STANDALONE_METHOD`.

The primary tolerance is fixed at Hit@±1. Required accompanying metrics include per-position Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE. Mandatory baselines are random, fixed, mean, median, last, frequency, and statistical AR(1).

All configured seeds are retained and summarized; best-seed-only selection is not part of the campaign. Prediction records are persisted and SHA-256 sealed with `actuals_known=false` before the scoring stage reads corresponding actuals.

See `docs/UNIFIED_EVALUATION_CAMPAIGN.md` for the execution contract.

## Hit@±1 constrained decoder

PR #249 added an explicit select-game decoder objective:

```text
DecodeObjective.MAP
DecodeObjective.WITHIN_TAU
```

`WITHIN_TAU` maximizes additive expected positional Hit@±tau utility subject to the legal strictly increasing select-game constraint. Focused tests cover exact IID-null optima for mini/loto6/loto7/bingo5, brute-force agreement on a reduced geometry, MAP compatibility and fail-closed probability validation.

This is a decoder objective implementation. It is **not** evidence that lottery draws are non-IID, not a promise of OOF improvement, and not a Holdout/Prospective result.

## What has not been established

The following claims are **not** supported by this repository snapshot:

- all 174 registered entries successfully execute on all six games;
- all 174 entries are independent forecast models;
- all registered entries are runtime-certified on the target host;
- a complete real-data 174 × 6 accuracy campaign has been executed;
- the within-tau decoder improves every model's real OOF score;
- a model beats every mandatory baseline;
- a champion has passed formal Holdout;
- Prospective evidence authorizes promotion or production binding.

A complete campaign matrix means every requested combination has a recorded result row; it does not mean every row succeeded.

## Runtime/capability documentation

Use these code-grounded/current references:

- `docs/MODEL_EXECUTION_MATRIX.md`
- `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md`
- `docs/LIBRARY_RUNTIME_CAPABILITIES.md`
- `docs/TSFM_RUNTIME_CAPABILITIES.md`
- `docs/MODEL_INVENTORY.md`
- `docs/UNIFIED_EVALUATION_CAMPAIGN.md`

Historical runtime evidence remains historical evidence. Do not rewrite old observations to match a newer aggregate.

## Scientific work still open

### Timer Base 84M — Issue #239

Status remains OOF-focused. Runtime certification and an evaluation foundation exist, but this status document does not claim that formal leakage-safe real-data OOF has completed. Holdout and Prospective remain closed.

### Timer-S1 — Issue #118

PR-A is historical/merged, but PR-B immutable provenance, remote-code review, isolated runtime, real inference, GPU evidence, reload reproducibility, and certification remain an open workstream. No OOF/accuracy/promotion claim follows from that issue.

## Documentation interpretation rules

1. Live GitHub state is newer than this snapshot once time advances beyond `as_of`.
2. Code/config determine executable capability; prose does not create runtime support.
3. Runtime certification does not establish lottery-domain forecast quality.
4. OOF does not authorize Holdout; Holdout does not authorize Prospective; Prospective does not automatically authorize promotion.
5. Historical verification reports remain point-in-time evidence and should be superseded by links rather than rewritten as if they were current runs.
