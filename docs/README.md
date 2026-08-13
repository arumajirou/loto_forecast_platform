# Documentation map

```text
status_class: LIVE_ENTRYPOINT
code_audit_base_sha: 0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
as_of: 2026-08-13T18:10+09:00
```

このページは、**どの質問にどの資料を正本として使うか**を示します。コード、generated inventory、runtime evidence、scientific evidence、exact-PR evidence、operator-local evidence、historical reportを同じ「現在値」として扱わないでください。

## Start here

| Question | Canonical reference |
|---|---|
| platform全体を最短で把握したい | [`../README.md`](../README.md) |
| 今までの主要改修を一覧したい | [`CURRENT_CHANGE_SUMMARY.md`](CURRENT_CHANGE_SUMMARY.md) |
| 現在のrepository/scientific状態 | [`STATUS.md`](STATUS.md) |
| 現在の検証境界 | [`CURRENT_VERIFICATION_REPORT.md`](CURRENT_VERIFICATION_REPORT.md) |
| 次に作業する人向け引継ぎ | [`CURRENT_HANDOFF.md`](CURRENT_HANDOFF.md) |
| library/model/引数/実行laneを詳しく引きたい | [`LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](LIBRARY_MODEL_COMPATIBILITY_MATRIX.md) |
| 実行・運用capability | [`CAPABILITIES_AND_OPERATIONS.md`](CAPABILITIES_AND_OPERATIONS.md) |
| execution evidence addendum | [`CURRENT_MODEL_EXECUTION_ADDENDUM.md`](CURRENT_MODEL_EXECUTION_ADDENDUM.md) |
| Darts current state | [`darts/CURRENT_STATE_DARTS.md`](darts/CURRENT_STATE_DARTS.md) |
| skforecast operator-local runtime evidence | [`SKFORECAST_RUNTIME_CERTIFICATION.md`](SKFORECAST_RUNTIME_CERTIFICATION.md) |
| dynamic scikit-learn | [`SKLEARN_ALL_MODELS.md`](SKLEARN_ALL_MODELS.md) |
| parallel Broad campaign | [`PARALLEL_UNIFIED_CAMPAIGN.md`](PARALLEL_UNIFIED_CAMPAIGN.md) |
| LightGBM GPU backend | [`LIGHTGBM_GPU_CERTIFICATION.md`](LIGHTGBM_GPU_CERTIFICATION.md) |
| TSFM runtime evidence | [`TSFM_RUNTIME_CAPABILITIES.md`](TSFM_RUNTIME_CAPABILITIES.md) |
| formal requirements | [`REQUIREMENTS.md`](REQUIREMENTS.md) |
| external specification | [`SPECIFICATION.md`](SPECIFICATION.md) |
| architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| data/leakage contract | [`DATA_CONTRACT.md`](DATA_CONTRACT.md) |
| test/verification plan | [`TEST_PLAN.md`](TEST_PLAN.md) |
| operations runbook | [`CURRENT_RUNBOOK.md`](CURRENT_RUNBOOK.md) |
| current documentation artifacts | [`CURRENT_ARTIFACT_MANIFEST.md`](CURRENT_ARTIFACT_MANIFEST.md) |
| documentation freshness rules | [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md) |

## Current denominator map

```text
Broad v1                           = 174 frozen identities
Probabilistic effective v1         = 76 identities
Combined Broad + Probabilistic     = 250 accounting identities
Current Broad campaign plan        = 174 × 6 = 1,044 rows
Combined accounting × six games    = 250 × 6 = 1,500 cells
Expanded v2 Phase 1                = 210 implementation identities
Canonical games                    = 6
```

The current `loto3 campaign --plan-only` uses the Broad catalog and therefore plans **1,044** rows. It does not automatically append the separate probabilistic 76 identities. The 250/1,500 values are combined accounting denominators.

## Current platform surfaces

### Six-game geometry

```bash
uv run loto3 games
```

Canonical keys:

```text
mini loto6 loto7 bingo5 numbers3 numbers4
```

### Broad inventory

```bash
uv run loto3 catalog --counts
uv run loto3 catalog --library neuralforecast
```

The Broad inventory is 174 entries. It is a frozen planning/inventory denominator, not a success counter.

### Shared execution inventory

```bash
uv run loto models list --format table
```

This corresponds to the shared executable catalog and is narrower/different from broad inventory and provider-specific source inventories.

### Broad development campaign

```bash
uv run loto3 campaign --output unused --plan-only

uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Every requested Broad model × game pair receives an explicit row. `FAILED`, `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `PARTIAL_SEEDS` and `NON_STANDALONE_METHOD` are valid evidence states and are not hidden.

Primary metric is Hit@±1, accompanied by position/all-position Hit@±1, MAE, MSE and RMSE. Mandatory baselines and all configured seeds are retained. Predictions are sealed before the corresponding actual is read for scoring.

### Parallel campaign wrapper

```bash
uv run python -m loto.evaluation.parallel_campaign --help
```

This adds game-level process parallelism/resource controls. It does not change the Broad denominator or silently combine the separate probabilistic catalog.

### Dynamic scikit-learn

```bash
uv run loto-sklearn list
```

This denominator depends on the installed scikit-learn version and does not rewrite Broad v1.

## Model/inventory surfaces

```text
src/loto/models/catalog_full.py
  Broad v1 = 174 frozen identities

src/loto/models/catalog.py
  shared executable ModelSpec catalog

src/loto/models/implementation_catalog.py
  separate Expanded v2 implementation identities

factory.py + workers.py
  shared candidate/position/foundation dispatch

models/providers/**
  shared/provider-specific model execution

*_campaign/** + adapters/** + environments/**
  isolated/provider-specific certification lanes

probabilistic/**
  separate effective probabilistic v1 = 76 under current loader behavior

audit/**
  point-in-time exact runtime evidence
```

Therefore:

```text
REGISTERED
!= IMPLEMENTED
!= SHARED_ROUTABLE / PROVIDER_ROUTABLE
!= RUNTIME_CERTIFIED
!= OOF_EVALUATED
!= HOLDOUT_EVALUATED
!= PROSPECTIVE_EVALUATED
!= PROMOTION_ELIGIBLE
```

## Current important evidence boundaries

### sktime

```text
141 discovered/importable
4 formal P1 models
4/4 formal fit/predict/save-load PASS
```

141 discovered/importable is not 141 runtime-certified.

### skforecast

`SKFORECAST_RUNTIME_CERTIFICATION.md` is `OPERATOR_LOCAL_EVIDENCE` against an exact source head. It does not close current-main Expanded v2 #289 / TAJ-32.

### Darts

Current main contains provider/campaign foundations. A separate local exact-worktree has Torch bootstrap + NLinear/DLinear real GPU fit/predict evidence. This is `LOCAL_VERIFIED / MAIN_PENDING`; #286 / TAJ-27 remains active.

### GluonTS

Draft PR #309 has exact-head P6/P7 CPU lifecycle evidence for 18/18 model lifecycles and P7D `VALID/VERIFIED`, but the PR is main-pending. Exact PR evidence is not current-main certification.

## Document classes

### Live entry points / design contracts

Update when current behavior changes:

- root `README.md`;
- this `docs/README.md`;
- `CAPABILITIES_AND_OPERATIONS.md`;
- `LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`;
- `REQUIREMENTS.md`;
- `SPECIFICATION.md`;
- `ARCHITECTURE.md`;
- `DATA_CONTRACT.md`;
- `TEST_PLAN.md`;
- `CURRENT_RUNBOOK.md`;
- `DOCUMENTATION_POLICY.md`.

### Audited current-state documents

- `STATUS.md`;
- `CURRENT_CHANGE_SUMMARY.md`;
- `CURRENT_HANDOFF.md`;
- `CURRENT_VERIFICATION_REPORT.md`;
- `CURRENT_MODEL_EXECUTION_ADDENDUM.md`;
- `CURRENT_ARTIFACT_MANIFEST.md`.

Live GitHub/code state wins after their `as_of` time.

### Generated inventory

Generated inventory files are not hand-edited to manufacture routing/runtime success. Source code/runtime discovery is authoritative for derived counts.

### Runtime/scientific evidence

Runtime certification applies only to the exact model/revision/environment/source it exercised. OOF/Holdout/Prospective evidence applies only to the exact protocol/data/model identity that generated it.

### Historical evidence

Older verification reports, handoffs and provider artifacts preserve their original observations. Add supersession/current-state references rather than rewriting historical facts.

### Immutable artifacts

Prediction/protocol locks, `SHA256SUMS`, model/data manifests and release bundles must not be silently regenerated in place.

## Scientific gate order

```text
IMPLEMENTED
-> RUNTIME_CERTIFIED
-> DEVELOPMENT OOF
-> explicit Holdout authorization
-> HOLDOUT
-> sealed PROSPECTIVE prediction
-> later actual scoring
-> PROMOTION_ELIGIBLE
-> HUMAN APPROVAL
```

`champion=null` / `NO_MODEL_BEATS_BASELINE` are valid outcomes. Implementation or runtime completion does not open Holdout or Prospective.
