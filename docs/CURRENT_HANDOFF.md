# Current Handoff

```text
status_class: AUDITED_CURRENT_STATE
audit_time: 2026-08-13T18:10+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
source_of_truth: live GitHub + repository code/config + retained evidence + explicitly classified exact-head/operator-local evidence
```

## Start here

1. `README.md`
2. `docs/STATUS.md`
3. `docs/CURRENT_CHANGE_SUMMARY.md`
4. `docs/CURRENT_VERIFICATION_REPORT.md`
5. `docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`
6. `docs/CAPABILITIES_AND_OPERATIONS.md`
7. `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md`
8. `docs/darts/CURRENT_STATE_DARTS.md`
9. `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`
10. `docs/PARALLEL_UNIFIED_CAMPAIGN.md`
11. `docs/CURRENT_RUNBOOK.md`
12. `docs/REQUIREMENTS.md`
13. `docs/SPECIFICATION.md`
14. `docs/ARCHITECTURE.md`
15. `docs/DATA_CONTRACT.md`
16. `docs/TEST_PLAN.md`

## Current repository boundary

```text
main=0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
latest merged documentation PR=#313
PR #310 merge=4f4f8579c6bcc05e25ea472e48385114bb56c71d
PR #312 merge=063120fd9b07d07548442edbce480a6d068f9f43
PR #311 merge=9623f2a562d21b4f9be84c392429885a51a72fe1
PR #313 merge=0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
```

PR numbering is not guaranteed to match merge chronology. Re-fetch live main before mutation.

## Denominators — do not mix them

```text
Broad v1 = 174 identities (frozen)
Probabilistic effective v1 = 76 identities
Combined Broad + Probabilistic accounting = 250 identities
Current `loto3 campaign` Broad plan = 174 × 6 = 1,044 rows
Combined accounting × six games = 250 × 6 = 1,500 cells
Expanded v2 Phase 1 = 210 implementation identities
canonical games = 6
```

The key correction from PR #311 is that **current `loto3 campaign --plan-only` plans Broad 174 only**. It does not automatically append the separate probabilistic 76. Do not describe current single-command output as 1,500 rows.

Useful commands:

```bash
uv run loto3 games
uv run loto3 catalog --counts
uv run loto3 catalog
uv run loto models list
uv run loto3 campaign --output unused --plan-only
uv run python -m loto.evaluation.parallel_campaign --help
uv run loto-sklearn list
```

## Evidence rules

Never reduce state to one `available` boolean.

```text
REGISTERED
!= ROUTABLE
!= RUNTIME_CERTIFIED
!= DEVELOPMENT_OOF
!= HOLDOUT
!= PROSPECTIVE
!= PROMOTION_ELIGIBLE
```

For runtime claims verify, as applicable:

```text
load
input contract
inference
output shape
finite values
device
GPU PID / VRAM
CPU fallback
serialize / reload / re-predict
artifact identity / SHA-256
```

`EXACT_HEAD_VERIFIED`, `OPERATOR_LOCAL_EVIDENCE`, and `LOCAL_VERIFIED / MAIN_PENDING` must remain visibly different from merged current-main certification.

## Current runtime highlights

### scikit-learn / boosting

- dynamic `loto-sklearn` provider is merged;
- isotonic calibrated logistic route is implemented;
- XGBoost GPU route has bounded exact-source runtime evidence;
- CatBoost GPU route has bounded exact-source runtime evidence;
- LightGBM OpenCL `device_type="gpu"` is verified/routed;
- current LightGBM build does **not** support the CUDA tree learner and must remain fail-closed for that claim.

### sktime

```text
sktime=1.0.1
141 discovered/importable
53 core-compatible
88 optional-dependency-declared
4 formal P1 models
4/4 fit/predict/save-load/formal verification PASS
```

Do not call all 141 runtime-certified.

### skforecast 0.23.0

Maintainer-host exact-source evidence covers recursive/direct/multi-series/statistical/backtesting/persistence, optional tree estimators, RNN CUDA/CPU fallback, Chronos-2, TimesFM, TabICL and bounded Moirai/TabPFN paths.

Use `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` for exact classification. This evidence is not a substitute for #289 / TAJ-32 repository inventory/routing acceptance.

### Darts — #286 / TAJ-27

PR #311 updated the current Darts documentation and tracking. Current main has provider/campaign foundations. A later exact local worktree has:

```text
torch=2.9.1+cu130
CUDA=13.0
pytorch-lightning=2.6.5
official bootstrap=PASS
NLinear actual GPU fit/predict=VERIFIED
DLinear actual GPU fit/predict=VERIFIED
```

Classification remains `LOCAL_VERIFIED / MAIN_PENDING`. Current main `smoke_models` is not a universal real fit/predict certification. Continue source-complete identity/routing/formal smoke work under #286 / TAJ-27.

### GluonTS — #288 / TAJ-29 / Draft #309

Current exact-head runtime evidence:

```text
PR #309 state=OPEN
draft=true
mergeable=true
head=edba730a4f2c944c1ccc0bee510f7ce34833b6c3
P6 latest=9/9 VERIFIED
P6 compat=9/9 VERIFIED
P6 total=18/18 VERIFIED
P7D=VALID / VERIFIED
p8_eligible=true
ci=QUEUED
windows-portability-ci=QUEUED
```

This is exact-head CPU lifecycle evidence, not current-main certification. Do not treat `p8_eligible=true` as permission to skip integration/current-source verification.

### Toto 22M

PR #296 is merged, but formal runtime certification remains blocked by #297 native-Linux external provider PID / VRAM / release evidence.

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
```

## Highest-value open work

### #286 / TAJ-27 — Darts Expanded v2

1. freeze source/revision;
2. derive source-complete forecasting identities;
3. preserve separate `algorithm_id` and `implementation_id`;
4. classify dependencies, probabilistic/covariate/multivariate/GPU/save-load capabilities;
5. route supported implementations explicitly;
6. retain non-routable/unsupported rows;
7. formalize real fit/predict/save-load smokes beyond bounded local NLinear/DLinear evidence;
8. keep Broad v1=174 unchanged.

### #288 / TAJ-29 — GluonTS Expanded v2

1. re-fetch current main and #309 exact head;
2. inspect queued/failed/cancelled Actions by actual execution state;
3. preserve expected-head SHA on merge;
4. never treat cancelled dashboards as runtime certification;
5. after integration, verify merged-main source identity before downstream evaluation.

### #289 / TAJ-32 — sktime + skforecast Expanded v2

Promote deterministic source/runtime inventories into explicit implementation identities without turning operator-local evidence into automatic current-main certification.

### #292 / TAJ-36 — final Expanded v2 freeze/runtime matrix

Do not freeze the final denominator until prerequisite expansion phases have stable source identities/routing metadata.

### Other gates

- #265/#266: complete campaign/runtime work, preserving Broad vs probabilistic denominator distinctions;
- #297: Toto 22M native-Linux formal GPU process/release evidence;
- #281/TAJ-30: TabPFN-TS-3 authentication/license/runtime;
- #272: Windows path portability;
- #239: Timer Base 84M development OOF;
- #118: Timer-S1 continuation;
- #275: GitHub Pages activation.

## Scientific protocol reminders

Primary metric: **Hit@±1**.

Retain:

- MAE / MSE / RMSE;
- position-wise Hit@±1;
- all-position Hit@±1;
- Random/fixed/mean/median/last/frequency/statistical baselines;
- every configured seed with mean/variance/worst;
- chronological folds;
- Train-only preprocessing/HPO;
- prediction SHA-256 + timestamp before corresponding actual reads.

Required scientific order:

```text
development OOF
-> review
-> explicit Holdout authorization
-> Holdout
-> explicit Prospective protocol
-> sealed future prediction
-> later actual scoring
-> promotion eligibility
-> human approval
```

Holdout and Prospective are **CLOSED**.

## Before any GitHub mutation

1. fetch live main/head/base;
2. confirm duplicate branch/PR/issue state;
3. compare exact changed files;
4. preserve expected-head SHA for merge;
5. inspect reviews and unresolved threads;
6. classify Actions as executed/queued/cancelled/failed, not by appearance;
7. do not merge unrelated changes;
8. after merge, verify main contains the intended result.
