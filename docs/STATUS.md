# Repository Status

```text
status_class: AUDITED_CURRENT_STATE
as_of: 2026-08-13T18:10+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
latest_merged_documentation_pr: 313
source_of_truth: current GitHub main + code/config + retained evidence + explicitly classified exact-head/operator-local evidence
```

## Executive status

- Default branch: `main`.
- Broad v1 remains frozen at **174** identities.
- Effective Probabilistic v1 is **76** identities.
- Broad + Probabilistic combined accounting denominator is **250** identities.
- Current `loto3 campaign --plan-only` uses the Broad catalog only: **174 × 6 = 1,044** planning units.
- **250 × 6 = 1,500** is the combined Broad+Probabilistic accounting denominator, not the row count produced by the current single Broad campaign command.
- Expanded v2 Phase 1 is merged with **210** implementation identities after replacing the AutoGluon umbrella with 37 source-backed identities.
- Six canonical game geometries are implemented.
- Hit@±1 remains the primary scientific metric.
- Parallel campaign execution, resource-aware scheduling, live progress, fail-visible rows, prediction sealing and aggregate artifacts are implemented.
- Dynamic all-estimator scikit-learn provider is merged.
- XGBoost / CatBoost GPU routing and LightGBM OpenCL GPU routing are merged with bounded runtime evidence.
- sktime 1.0.1 P1 fixed four-model matrix is formally verified on exact source; 141 registry discovery/importability is a different denominator.
- skforecast 0.23.0 has substantial **operator-local** runtime evidence; current-main Expanded v2 inventory/routing remains open under #289 / TAJ-32.
- Darts current docs now distinguish merged provider/campaign foundation from local Torch/NLinear/DLinear GPU evidence; #286 / TAJ-27 remains in progress.
- GluonTS Draft PR #309 has **exact-head** P6/P7 CPU lifecycle evidence: latest 9/9 + compat 9/9 = 18/18, P7D `VALID/VERIFIED`, but it is not merged current-main certification.
- Holdout: **CLOSED**.
- Prospective: **CLOSED**.
- Automatic promotion/retraining/registry writes: **FORBIDDEN**.
- Champion: **not authorized by current evidence**.

## State hierarchy

Do not compress these stages into one `available` flag:

```text
REGISTERED
-> ROUTABLE
-> DEPENDENCY / IDENTITY VERIFIED
-> LOAD / INPUT / INFERENCE VERIFIED
-> SHAPE / FINITE VERIFIED
-> DEVICE / PID / VRAM / FALLBACK VERIFIED when applicable
-> LIFECYCLE VERIFIED when applicable
-> RUNTIME_CERTIFIED
-> LOTTERY_COMPATIBLE
-> DEVELOPMENT OOF EVALUATED
-> HOLDOUT EVALUATED
-> PROSPECTIVE EVALUATED
-> PROMOTION ELIGIBLE
-> HUMAN APPROVAL
```

Evidence labels:

| Label | Meaning |
|---|---|
| `VERIFIED` | claim verified for the stated current-code/evidence scope |
| `PARTIALLY_VERIFIED` | only a subset/lane/environment is verified |
| `EXACT_HEAD_VERIFIED` | verified on a specific PR/source SHA; merge/current-main is separate |
| `OPERATOR_LOCAL_EVIDENCE` | maintainer-host exact-source evidence; not repository-retained current-main certification |
| `LOCAL_VERIFIED / MAIN_PENDING` | bounded local exact-worktree success waiting for publication/integration |
| `EXECUTION_PENDING` | implementation/plan exists but denominator has not completed |
| `BLOCKED` | explicit dependency/license/runner/policy/artifact gate |
| `NOT CERTIFIED` | no accepted success evidence; fail-closed |

## Inventory and planner boundaries

```text
Broad v1                           = 174
Probabilistic effective v1         = 76
Combined Unified accounting        = 250
Current Broad campaign planner     = 174 × 6 = 1,044
Combined accounting × six games    = 250 × 6 = 1,500
Expanded v2 Phase 1                = 210
Canonical games                    = 6
```

`src/loto/models/catalog_full.py` derives Broad counts from `build_catalog()` / `catalog_counts()` rather than using README as count authority. `src/loto/models/implementation_catalog.py` deliberately keeps Expanded v2 separate so expansion does not rewrite Broad v1. The probabilistic loader appends four PPL-02 fallback identities when absent from the YAML source, producing the current effective probabilistic denominator.

The important execution boundary corrected in PR #311 is:

```text
current `loto3 campaign --plan-only`
= Broad 174 × 6
= 1,044 rows
```

It does **not** automatically append the separate probabilistic 76 identities. The combined 250 / 1,500 values are accounting/planning denominators across the two surfaces.

## Recent merged implementation/documentation sequence

| PR | Main SHA | Current interpretation |
|---|---|---|
| #268 | `81bd4f8123d2a72226347c1cd2220fe95a17d750` | statistical/causal analysis foundation |
| #270 | `775274cc22cf6701f148da80dfe86cb1bd099a7e` | resource-aware broad runner / runtime evidence serialization |
| #273 | `522253eab194b81a8d804236d5477a4bd9bacd68` | repository observability / structured work intake |
| #274 | `c57731e17b43f8f5d9e038c75017aa9ce83fd5e9` | visual dashboard build + Pages gate |
| #276 | `4eabd68d422baefe5180c747bb4bdc83df1caba2` | GitHub operations control center |
| #277 | `1df090fa34fbf1d32ec7000b25689c49e0c20074` | scheduler stabilization |
| #293 | `f04cd876f61b3c2ef85529082a6ba812f7859f6f` | Expanded v2 foundation / AutoGluon expansion |
| #295 | `951f5f57d8e975bd9b1dbf41a213569733a340e4` | Toto family manifest / 22M provenance |
| #296 | `abe7e02cdfc900618c83b21c922b4fd3f078b036` | Toto 22M runtime certification infrastructure |
| #299 | `05eba49dad8c0700c303783267784cfde081e419` | implementation-grounded README audit |
| #300 | `a7eb50ca534c4880681d5febab193b0c2692f50c` | library/model compatibility matrix |
| #301 | `3cc73dbad8c437bc5b8c18b20d00fb59ba60522d` | dynamic scikit-learn provider |
| #302 | `7d75dadc8c9da6292988ad7b4691e020dc90cc1e` | parallel Broad campaign / live progress |
| #303 | `b9be417463395642521a9955b055fdeac5aa1f8d` | isotonic calibrated logistic routing |
| #304 | `de1444af8915c69e466c0ded16c972e7dbabff0f` | XGBoost/CatBoost GPU lease routing |
| #305 | `a03053eabf838d0e9583b49aac1aa3c2f40de6b0` | LightGBM accelerator capability probe |
| #306 | `feb4ea5ec6c63c1e3ceab26bcf9d3bc731d14add` | LightGBM OpenCL GPU routing |
| #307 | `ed7d6c8151254653d44296b608457200ac80c5ce` | sktime P1 normalization fix |
| #308 | `932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf` | README current-state reconciliation |
| #310 | `4f4f8579c6bcc05e25ea472e48385114bb56c71d` | current-state docs + skforecast operator-local evidence |
| #312 | `063120fd9b07d07548442edbce480a6d068f9f43` | library/model matrix post-#310 alignment |
| #311 | `9623f2a562d21b4f9be84c392429885a51a72fe1` | Darts evidence + Broad planner denominator correction |
| #313 | `0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d` | README audit-boundary stabilization after #311 |

PR numbers are not a chronological guarantee; merge SHA/current main is authoritative. See `docs/CURRENT_CHANGE_SUMMARY.md` for the grouped explanation.

## Library/runtime highlights

### scikit-learn / boosting

- dynamic `loto-sklearn` provider is merged;
- Broad isotonic calibrated logistic route is implemented;
- XGBoost GPU constructor/runtime routing has bounded exact-source evidence;
- CatBoost GPU constructor/runtime routing has bounded exact-source evidence;
- LightGBM 4.7.0 current build is **not CUDA tree-learner capable**;
- LightGBM OpenCL `device_type="gpu"` is verified and routed.

### sktime

```text
sktime=1.0.1
registry discovered/importable=141
core-compatible=53
optional-dependency-declared=88
formal P1 models=4
4/4 fit/predict/save-load/formal verification PASS
```

This does not certify all 141 forecasters.

### skforecast

Maintainer-host exact-source evidence covers core recursive/direct/multi-series/statistical/backtesting/persistence surfaces, RNN CUDA/CPU fallback, Chronos-2, TimesFM, TabICL and bounded Moirai/TabPFN paths. This remains `OPERATOR_LOCAL_EVIDENCE`; #289 / TAJ-32 is still the repository integration gate.

### Darts

PR #311 corrected the previous blanket `REAL_DARTS_RUNTIME_BLOCKED` wording. Current main has provider/campaign foundations. A separate local exact worktree has verified Torch bootstrap plus NLinear/DLinear real GPU fit/predict, but these changes/evidence remain `LOCAL_VERIFIED / MAIN_PENDING`. GitHub #286 / TAJ-27 remains in progress for source-complete inventory/routing/formal smokes.

### GluonTS Draft #309

Live PR state at this audit:

```text
state=OPEN
draft=true
mergeable=true
head=edba730a4f2c944c1ccc0bee510f7ce34833b6c3
latest lane=9/9 VERIFIED
compat lane=9/9 VERIFIED
P6 total=18/18 VERIFIED
P7D evidence_state=VALID
P7D certification_status=VERIFIED
P7D verification_state=VERIFIED
p8_eligible=true
current-main integration=false
```

GitHub `ci` and `windows-portability-ci` remain queued at this documentation snapshot. Cancelled dashboard workflows are not interpreted as code/test PASS or failure. This is an exact-head CPU lifecycle claim, not GluonTS GPU/OOF/current-main certification.

### Toto 22M

PR #296 merged pinned runtime-certification infrastructure, but formal certification remains fail-closed pending #297 native-Linux external provider PID / per-process VRAM / post-exit release evidence.

## Campaign execution surface

Current Broad planner:

```bash
uv run loto3 campaign --output unused --plan-only
# expected denominator: 174 × 6 = 1,044
```

Broad development execution:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Parallel wrapper:

```bash
uv run python -m loto.evaluation.parallel_campaign --help
```

Failures/non-routable/unsupported rows remain visible. `matrix_complete=true` means required result-row coverage for the executed surface, not universal model success or forecast superiority.

## Scientific contract

Primary:

```text
Hit@±1
```

Required companions:

```text
MAE
MSE
RMSE
position-wise Hit@±1
all-position Hit@±1
```

Mandatory baselines:

```text
Random
fixed
mean
median
last / recent
frequency
statistical
```

Chronological Train / Validation / Holdout / Prospective ordering is mandatory. Preprocessing/HPO fits only within allowed Train data. All configured seeds are retained with mean/variance/worst statistics. Predictions are sealed with SHA-256 + timestamp before the corresponding actual is read.

## Major active gates

| Gate | Current interpretation |
|---|---|
| #265 / #266 | Broad/runtime accounting campaigns remain incomplete; preserve current surface denominators |
| #286 / TAJ-27 | Darts Expanded v2 source-complete inventory/routing |
| #288 / TAJ-29 | GluonTS Expanded v2; #309 exact-head verified but main-pending |
| #289 / TAJ-32 | sktime + skforecast Expanded v2 inventory/routing |
| #292 / TAJ-36 | Expanded v2 final count freeze and full six-game runtime matrix |
| #297 | Toto 22M native-Linux formal GPU process/release evidence |
| #281 / TAJ-30 | TabPFN-TS-3 authentication/license/runtime gate |
| #272 | Windows path portability |
| #239 | Timer Base 84M development OOF |
| #118 | Timer-S1 continuation |
| #275 | GitHub Pages activation |

Live GitHub/Linear state is authoritative if it moves after this snapshot.

## What is not established

This snapshot does not establish:

- all Broad 174 models succeeding on all six games;
- a single current campaign automatically running Broad 174 + probabilistic 76;
- final Expanded v2 source/runtime completion;
- all registered models as routable;
- all routable models as runtime-certified;
- universal GPU execution;
- all-model OOF superiority;
- Holdout completion;
- Prospective completion;
- champion selection;
- production promotion.
