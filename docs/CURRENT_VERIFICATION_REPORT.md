# Current Verification Report

```text
status_class: AUDITED_CURRENT_STATE
audit_time: 2026-08-13T18:10+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
scope: current merged implementation + retained evidence + explicitly separated exact-head/operator-local runtime evidence
```

## Verdict

```text
SIX_GAME_GEOMETRY=VERIFIED
BROAD_V1_174=FROZEN
PROBABILISTIC_EFFECTIVE_V1_76=VERIFIED_LOADER_BEHAVIOR
COMBINED_UNIFIED_ACCOUNTING_250=VERIFIED_DENOMINATOR
CURRENT_BROAD_CAMPAIGN_PLAN_1044=VERIFIED_CONTRACT
CURRENT_SINGLE_CAMPAIGN_PLAN_1500=false
PARALLEL_BROAD_CAMPAIGN=IMPLEMENTED
SCIKIT_LEARN_DYNAMIC_PROVIDER=IMPLEMENTED
XGBOOST_GPU_ROUTE=VERIFIED_ON_BOUNDED_EXACT_SOURCE
CATBOOST_GPU_ROUTE=VERIFIED_ON_BOUNDED_EXACT_SOURCE
LIGHTGBM_OPENCL_GPU_ROUTE=VERIFIED_ON_BOUNDED_EXACT_SOURCE
LIGHTGBM_CUDA=NOT_CERTIFIED
SKTIME_P1_FIXED_4=VERIFIED_ON_EXACT_SOURCE
SKFORECAST_0_23_OPERATOR_RUNTIME=PARTIALLY_VERIFIED
SKFORECAST_EXPANDED_V2_REPOSITORY_INTEGRATION=OPEN
DARTS_LOCAL_TORCH_NLINEAR_DLINEAR=LOCAL_VERIFIED_MAIN_PENDING
DARTS_EXPANDED_V2=IN_PROGRESS
GLUONTS_PR_309_CPU_LIFECYCLE=EXACT_HEAD_VERIFIED_18_OF_18
GLUONTS_PR_309_MAIN_INTEGRATION=PENDING
HOLDOUT=CLOSED
PROSPECTIVE=CLOSED
AUTOMATIC_PROMOTION=FORBIDDEN
CHAMPION=NOT_AUTHORIZED
```

## Evidence classes

| Class | Meaning |
|---|---|
| `CURRENT_CODE` | behavior visible in current repository code/config |
| `REPOSITORY_RETAINED` | tests/workflows/artifacts retained through repository/GitHub evidence |
| `EXACT_PR_SOURCE` | exact-head worktree/CI/runtime evidence for a specific PR SHA |
| `OPERATOR_LOCAL` | maintainer-host runtime evidence for an exact source SHA; not automatically current-main certification |
| `LOCAL_VERIFIED_MAIN_PENDING` | bounded local exact-worktree success waiting for publication/integration |
| `SCIENTIFIC_EVALUATION` | chronological development OOF / Holdout / Prospective evidence |

Evidence from one class is not silently promoted into another.

## Current merged baseline

Current documentation is audited from:

```text
main=0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
PR #310 merge=4f4f8579c6bcc05e25ea472e48385114bb56c71d
PR #312 merge=063120fd9b07d07548442edbce480a6d068f9f43
PR #311 merge=9623f2a562d21b4f9be84c392429885a51a72fe1
PR #313 merge=0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
```

#310 refreshed current-state docs and skforecast operator evidence. #312 aligned the detailed matrix. #311 then corrected the Darts state and a key campaign-denominator error. #313 stabilized README audit metadata after #311.

## Inventory and planner verification

### Broad v1

`src/loto/models/catalog_full.py` builds the Broad registry programmatically and `catalog_counts()` derives totals from `build_catalog()`. Broad v1 remains frozen at **174** identities.

### Probabilistic v1

The current probabilistic loader contains four PPL-02 fallback rows and appends them when absent from the configured YAML. Current effective probabilistic denominator is **76**.

### Combined accounting

```text
Broad 174 + Probabilistic 76 = 250
250 × 6 canonical games = 1,500 accounting cells
```

This is a combined accounting denominator, not the current single Broad campaign execution plan.

### Current `loto3 campaign` planner

PR #311 corrected the current execution boundary:

```text
current `loto3 campaign --plan-only`
= Broad 174 identities × 6 games
= 1,044 planning rows
```

The current planner does not automatically append the separate probabilistic 76 identities. Therefore statements that a current single `loto3 campaign --plan-only` produces 1,500 rows are incorrect.

### Expanded v2

`src/loto/models/implementation_catalog.py` constructs a separate Expanded v2 inventory so implementation expansion cannot silently rewrite the frozen Broad denominator. Phase 1 expands the AutoGluon umbrella into 29 source models + 8 unique ensembles and yields **210** implementation identities.

## Runtime/execution verification

### Scheduler and parallel campaign

Merged code/history establish:

- deterministic resume/task fingerprints;
- explicit physical GPU assignment;
- weighted/resource-aware admission;
- timeout process-tree cleanup;
- outer worker cap;
- game-parallel Broad campaign wrapper;
- live progress state;
- fail-visible rows;
- aggregate artifacts/checksums.

These are execution-platform capabilities and do not certify every model.

### scikit-learn / tree boosting

- dynamic `loto-sklearn` provider: implemented;
- isotonic-calibrated logistic route: implemented;
- XGBoost GPU route: bounded exact-source runtime verified;
- CatBoost GPU route: bounded exact-source runtime verified;
- LightGBM 4.7.0 resolved build: CUDA tree learner not supported/certified;
- LightGBM OpenCL `device_type="gpu"`: bounded runtime verified and routed.

Documentation must not state generic “LightGBM CUDA supported” for the resolved build.

## sktime evidence boundary

Exact-source sktime 1.0.1 P1 evidence records:

```text
registry discovered = 141
registry importable = 141
core compatible = 53
optional dependency declared = 88
formal matrix models = 4
formal matrix result = 4/4 PASS
fit/predict = PASS
finite output = PASS
save/load/re-predict = PASS
artifact verification = PASS
```

This does not certify all 141 forecasters. Expanded v2 work remains tracked under #289 / TAJ-32.

## skforecast operator-local boundary

A maintainer-host sequence exercised skforecast 0.23.0 against exact source head:

```text
9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd
```

Recorded bounded evidence includes:

- recursive/direct/multi-series/statistical/backtesting/persistence surfaces;
- LightGBM/XGBoost/CatBoost estimator smoke on CPU;
- RNN LSTM/GRU actual CUDA plus LSTM CPU fallback;
- Chronos-2 GPU+CPU/exog/point/interval;
- TimesFM 2.5 GPU+CPU/point/interval/quantiles;
- Moirai-2 runtime only under a controlled unsupported dependency override;
- TabICL v2 GPU+CPU/exog/interval/quantile plus checkpoint hash evidence;
- TabPFN-TS V3 adapter/device/exog setup with inference blocked before weight access by invalid/expired authentication;
- T0 not executed in that sequence.

Therefore:

```text
SKFORECAST_OPERATOR_RUNTIME=PARTIALLY_VERIFIED
SKFORECAST_CURRENT_MAIN_EXPANDED_V2=NOT_COMPLETE
```

See `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`.

## Darts verification boundary

PR #311 corrected the stale Darts documentation. Current main contains the Darts provider/campaign/runtime foundation. GitHub #286 and Linear TAJ-27 remain active for source-complete Expanded v2 inventory/routing/formal smokes.

A separate later maintainer-host exact-worktree sequence established:

```text
darts=0.46.1
torch=2.9.1+cu130
CUDA=13.0
pytorch-lightning=2.6.5
official bootstrap=PASS
campaign_execution_allowed=true
NLinear actual GPU fit/predict=PASS
DLinear actual GPU fit/predict=PASS
```

This is `LOCAL_VERIFIED / MAIN_PENDING`, not a current-main all-Darts certification. Current-main `smoke_models` must not be described as universal real fit/predict certification. The source-complete inventory/routing gate remains open.

See `docs/darts/CURRENT_STATE_DARTS.md`.

## GluonTS exact-head verification boundary

Draft PR #309 remains open and main-pending. Exact PR head:

```text
edba730a4f2c944c1ccc0bee510f7ce34833b6c3
```

Retained exact-head evidence from the certification sequence establishes:

```text
latest lane models=9/9 VERIFIED
compat lane models=9/9 VERIFIED
verified model lifecycles=18/18
observed devices=['cpu']
P7D_RC=0
independent_VERIFY_RC=0
formal_audit_RC=0
evidence_state=VALID
certification_status=VERIFIED
verification_state=VERIFIED
p8_eligible=true
```

P7D archive:

```text
sha256=b56a94b0a0be29eff0a00960bdd9d6c0eeb3c85a13b166dce539b8dbc87b006b
```

Live GitHub state at this documentation audit:

```text
PR #309 state=OPEN
draft=true
mergeable=true
head_sha=edba730a4f2c944c1ccc0bee510f7ce34833b6c3
ci=QUEUED
windows-portability-ci=QUEUED
```

Cancelled dashboard/observability runs are not treated as code/test success or failure. Because the runtime PR is not integrated:

```text
GLUONTS_EXACT_HEAD_RUNTIME=VERIFIED
GLUONTS_CURRENT_MAIN_RUNTIME_FROM_PR_309=NOT_YET_ESTABLISHED
```

The evidence is CPU-pinned. It does not establish GluonTS GPU certification, OOF superiority, Holdout or Prospective performance.

## Toto 22M boundary

Merged PR #296 contains pinned family/runtime-certification infrastructure. Formal runtime certification remains fail-closed pending #297 native-Linux external provider PID / per-process VRAM / post-exit release evidence.

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
Holdout=CLOSED
Prospective=CLOSED
```

## Scientific verification boundary

Formal development evaluation requires:

```text
primary = Hit@±1
companions = MAE / MSE / RMSE / position Hit@±1 / all-position Hit@±1
baselines = Random / fixed / mean / median / last / frequency / statistical
split = chronological Train / Validation / Holdout / Prospective
preprocessing/HPO = Train-only within authorized data
seeds = retain all configured seeds + mean / variance / worst
forecast lock = SHA-256 + timestamp before corresponding actual read
```

Current scientific gates:

```text
HOLDOUT=CLOSED
PROSPECTIVE=CLOSED
AUTOMATIC_PROMOTION=FORBIDDEN
CHAMPION=NOT_AUTHORIZED
```

## Active verification gates

- #265 / #266 — complete runtime campaign work; preserve Broad vs probabilistic surface denominators;
- #286 / TAJ-27 — Darts Expanded v2 inventory/routing/publication;
- #288 / TAJ-29 — GluonTS Expanded v2 work; #309 exact-head runtime candidate remains main-pending;
- #289 / TAJ-32 — sktime + skforecast Expanded v2 inventories;
- #292 / TAJ-36 — Expanded v2 freeze + complete six-game runtime certification;
- #297 — Toto 22M native-Linux formal GPU process/release evidence;
- #281 / TAJ-30 — TabPFN-TS-3 authentication/license/runtime gate;
- #272 — native Windows path portability;
- #239 — Timer Base 84M development OOF;
- #118 — Timer-S1 continuation.

## What this report does not certify

- all Broad 174 models succeeding across all six games;
- a current single command automatically executing Broad 174 + probabilistic 76;
- final Expanded v2 runtime success;
- all registered models as routable;
- all routable models as runtime-certified;
- universal GPU success;
- all-model development OOF superiority;
- Holdout completion;
- Prospective completion;
- champion selection;
- production promotion.
