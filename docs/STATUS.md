# Repository Status

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T18:59+09:00
repository: arumajirou/loto_forecast_platform
source_of_truth: live GitHub state + code/config + exact-head CI evidence
base_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
superseded_by: NONE
```

This file is the current repository-status entry point. It is a point-in-time audit; live GitHub state takes precedence after the `as_of` time.

## Executive status

- Default branch: `main`.
- Audited main: `8430d9f507ba735bf1df69930e057c974752bfdb`.
- Unified all-model × all-game development evaluation is merged and callable through `uv run loto3 campaign`.
- Probability-bearing unified-campaign candidate estimators are now routed through family-specific Hit@±1/WITHIN_TAU decoding by PR #250; point-only workers remain point-only.
- The broad generated catalog remains a 174-entry inventory at this audit boundary; registration is not equivalent to shared routing, runtime certification, OOF completion, or promotion.
- Holdout: **CLOSED / NOT EVALUATED by this maintenance or decoder-routing work**.
- Prospective: **CLOSED / NOT EVALUATED**.
- Champion/promotion: **NONE AUTHORIZED**.
- Formal Timer Base 84M OOF work remains open in GitHub Issue #239.
- Timer-S1 PR-B immutable runtime/certification work remains open in GitHub Issue #118.

## Merge batch completed on 2026-08-10

| PR | Result | Main commit | Evidence boundary |
|---|---|---|---|
| #248 | MERGED | `aae45ba9294499f51cc5f1564de1c6ccf5814230` | exact pre-merge head passed Linux full CI and native Windows portability; unified campaign added |
| #244 | MERGED | `c12ca27048d25cdc869fa3cbbfa6e31c727eb529` | actions/checkout v7 workflow update; Linux and Windows exact-head checks passed |
| #242 | MERGED | `cc7ec5473730cfb18100bdfbb5228cf65e571b32` | Ray Tune updated to `>=2.56.1`; latest rebased head passed Linux and native Windows verification |
| #243 | MERGED | `b04f3e40baa1861a5b83da047bdef2655905bd52` | FastAPI updated to `>=0.141.1,<0.142`; exact-head Linux and Windows checks passed |
| #249 | MERGED | `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f` | explicit MAP/WITHIN_TAU constrained select decoder; Linux exact-head CI passed |
| #241 | MERGED | `cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300` | grouped Uvicorn/MLflow/Hypothesis/Ruff/GluonTS update; current-base Linux full CI passed; Windows lane was queued when GitHub accepted expected-head merge |
| #250 | MERGED | `8430d9f507ba735bf1df69930e057c974752bfdb` | unified candidate probability routing through family-specific WITHIN_TAU decoder; synchronized to current main, exact-head Linux full CI passed, review threads 0 |

GitHub Issue #247 was closed as completed after PR #248 merged.

## Open pull requests at audit cutoff

After the functional/dependency merge batch, the only open PR was the documentation refresh PR #251 itself. No unmerged implementation/dependency PR remained in the live open-PR search at the audit cutoff.

## Current dependency boundary

Audited main includes:

- FastAPI `>=0.141.1,<0.142` where declared;
- Ray Tune `>=2.56.1` in the `full` extra;
- Uvicorn 0.52.1 lane;
- MLflow 3.15.1 lane;
- Hypothesis 6.165.2 lane;
- Ruff 0.16.1 lane;
- GluonTS 0.17.0 lane;
- the corresponding committed `uv.lock`.

`uv.lock` remains the committed dependency lock and must stay consistent with `pyproject.toml`.

## Unified evaluation campaign

Primary command:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Plan-only inventory:

```bash
uv run loto3 campaign --output unused --plan-only
```

Canonical games are `mini`, `loto6`, `loto7`, `bingo5`, `numbers3`, and `numbers4`.

The campaign materializes every requested broad-catalog model × game pair exactly once and deliberately retains fail-visible states such as `FAILED`, `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `PARTIAL_SEEDS`, and `NON_STANDALONE_METHOD`.

The primary tolerance is Hit@±1. Required accompanying metrics include per-position Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE. Mandatory baselines are random, fixed, mean, median, last, frequency, and statistical AR(1). All configured seeds are retained and summarized; best-seed-only selection is not part of the campaign. Prediction records are persisted and SHA-256 sealed with `actuals_known=false` before scoring reads corresponding actuals.

## Decoder and candidate-routing state

PR #249 added explicit select-game `DecodeObjective.MAP` and `DecodeObjective.WITHIN_TAU` constrained decoding. PR #250 then connected probability-bearing unified-campaign candidate estimators to family-specific WITHIN_TAU decoding while preserving point-only worker routes and explicit decoder/distribution identities.

The candidate bridge is explicitly identified as a row-normalized slot-binary probability adapter rather than being mislabeled as a native categorical PMF. Decoder/distribution identities are persisted in runtime evidence attached to sealed seed evaluations.

These are implementation/theory and routing changes. They are **not** evidence that lottery draws are non-IID, not a promise of OOF improvement, and not Holdout/Prospective results.

## What has not been established

The following claims are **not** supported by this snapshot:

- all 174 registered entries successfully execute on all six games;
- all 174 entries are independent forecast models;
- all registered entries are runtime-certified on the target host;
- a complete real-data 174 × 6 accuracy campaign has been executed;
- the WITHIN_TAU decoder improves every model's real OOF score;
- a model beats every mandatory baseline;
- a champion has passed formal Holdout;
- Prospective evidence authorizes promotion or production binding.

A complete campaign matrix means every requested combination has a recorded result row; it does not mean every row succeeded.

## Runtime/capability documentation

Use these current/code-grounded references:

- `docs/MODEL_EXECUTION_MATRIX.md`
- `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md`
- `docs/LIBRARY_RUNTIME_CAPABILITIES.md`
- `docs/TSFM_RUNTIME_CAPABILITIES.md`
- `docs/MODEL_INVENTORY.md`
- `docs/UNIFIED_EVALUATION_CAMPAIGN.md`

Historical runtime evidence remains historical evidence. Do not rewrite old observations to match a newer aggregate.

## Scientific work still open

### Timer Base 84M — Issue #239

Status remains OOF-focused. Runtime certification and evaluation infrastructure do not establish that formal leakage-safe real-data OOF has completed. Holdout and Prospective remain closed.

### Timer-S1 — Issue #118

PR-B immutable provenance, remote-code review, isolated runtime, real inference, GPU evidence, reload reproducibility, and certification remain an open workstream. No OOF/accuracy/promotion claim follows from that issue.

## Documentation interpretation rules

1. Live GitHub state is newer than this snapshot once time advances beyond `as_of`.
2. Code/config determine executable capability; prose does not create runtime support.
3. Runtime certification does not establish lottery-domain forecast quality.
4. OOF does not authorize Holdout; Holdout does not authorize Prospective; Prospective does not automatically authorize promotion.
5. Historical verification reports remain point-in-time evidence and should be superseded by links rather than rewritten as if they were current runs.
