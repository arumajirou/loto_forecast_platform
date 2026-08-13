# Repository Status

```text
status_class: AUDITED_CURRENT_STATE
as_of: 2026-08-13T17:36+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf
source_of_truth: current GitHub main + code/config + retained evidence + explicitly classified operator-local evidence
```

## Executive status

- Default branch: `main`.
- Broad v1 remains frozen at **174** identities.
- Unified v1 remains **250** canonical identities / **1,500** model×game planning units.
- Expanded v2 Phase 1 is merged with **210** implementation identities after replacing the AutoGluon umbrella with 37 source identities.
- Six canonical game geometries are implemented.
- Hit@±1 remains the primary scientific metric.
- Parallel Unified Campaign, resource-aware scheduling, live progress, prediction sealing and fail-visible rows are implemented.
- Dynamic all-estimator scikit-learn provider is merged.
- XGBoost / CatBoost GPU routing and LightGBM OpenCL GPU routing are merged with exact-head runtime evidence.
- sktime 1.0.1 P1 fixed four-model matrix is formally verified on its exact PR source; registry discovery remains broader than runtime certification.
- skforecast 0.23.0 now has substantial **operator-local** runtime evidence, but the repository Expanded v2 inventory/routing work remains open under #289 / TAJ-32.
- Holdout: **CLOSED**.
- Prospective: **CLOSED**.
- Automatic promotion/retraining/registry writes: **FORBIDDEN**.
- Champion: **not authorized by current evidence**.

## Recent merged implementation sequence

| PR | Main SHA | Current interpretation |
|---|---|---|
| #268 | `81bd4f8123d2a72226347c1cd2220fe95a17d750` | statistical/causal analysis foundation |
| #270 | `775274cc22cf6701f148da80dfe86cb1bd099a7e` | resource-aware broad runner / runtime evidence serialization |
| #273 | `522253eab194b81a8d804236d5477a4bd9bacd68` | repository observability / structured work intake |
| #274 | `c57731e17b43f8f5d9e038c75017aa9ce83fd5e9` | visual dashboard build + Pages gate |
| #276 | `4eabd68d422baefe5180c747bb4bdc83df1caba2` | GitHub operations control center |
| #277 | `1df090fa34fbf1d32ec7000b25689c49e0c20074` | scheduler stabilization |
| #293 | `f04cd876f61b3c2ef85529082a6ba812f7859f6f` | Expanded v2 foundation / AutoGluon expansion |
| #295 | `951f5f57d8e975bd9b1dbf41a213569733a340e4` | Toto family manifest / 22M provenance gate |
| #296 | `abe7e02cdfc900618c83b21c922b4fd3f078b036` | Toto 22M runtime certification infrastructure |
| #299 | `05eba49dad8c0700c303783267784cfde081e419` | README implementation fact-check |
| #300 | `a7eb50ca534c4880681d5febab193b0c2692f50c` | library/model compatibility matrix |
| #301 | `3cc73dbad8c437bc5b8c18b20d00fb59ba60522d` | dynamic scikit-learn provider |
| #302 | `7d75dadc8c9da6292988ad7b4691e020dc90cc1e` | parallel campaign / live progress |
| #303 | `b9be417463395642521a9955b055fdeac5aa1f8d` | isotonic calibrated logistic routing |
| #304 | `de1444af8915c69e466c0ded16c972e7dbabff0f` | XGBoost/CatBoost GPU lease routing |
| #305 | `a03053eabf838d0e9583b49aac1aa3c2f40de6b0` | LightGBM accelerator capability probe |
| #306 | `feb4ea5ec6c63c1e3ceab26bcf9d3bc731d14add` | LightGBM OpenCL GPU routing |
| #307 | `ed7d6c8151254653d44296b608457200ac80c5ce` | sktime P1 normalization fix |
| #308 | `932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf` | README current-state reconciliation |

## Current model/runtime interpretation

Do not compress the following stages into one `available` flag:

```text
REGISTERED
-> ROUTABLE
-> DEPENDENCY/IDENTITY VERIFIED
-> LOAD / INPUT / INFERENCE VERIFIED
-> SHAPE / FINITE VERIFIED
-> DEVICE / PID / VRAM / FALLBACK VERIFIED
-> LIFECYCLE VERIFIED when applicable
-> RUNTIME_CERTIFIED
-> LOTTERY_COMPATIBLE
-> DEVELOPMENT OOF EVALUATED
-> HOLDOUT EVALUATED
-> PROSPECTIVE EVALUATED
-> PROMOTION ELIGIBLE
-> HUMAN APPROVAL
```

### skforecast 0.23.0

Operator-local execution against source head `9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd` established:

- core recursive/direct/multi-series/statistical/backtesting/persistence surfaces: PASS after correcting two harness/config assumptions;
- LightGBM/XGBoost/CatBoost recursive estimator smoke: PASS on CPU;
- RNN LSTM/GRU: actual CUDA PASS plus CPU fallback PASS;
- Chronos-2 small: GPU+CPU point/interval/exog PASS;
- TimesFM 2.5: GPU+CPU point/interval/quantile PASS;
- Moirai-2: runtime PASS only under an unsupported dependency metadata override; normal routability remains BLOCKED;
- TabICL v2: GPU+CPU/exog/interval/quantile PASS and checkpoint SHA-256 verified;
- TabPFN-TS v3 path: adapter/device/exog setup PASS but v3 inference blocked before weight download because the supplied Prior Labs token was invalid/expired;
- T0: not executed in this sequence.

This is **not** current-main Expanded v2 completion. See `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` and open #289 / TAJ-32.

### sktime

Current documented P1 evidence:

```text
sktime=1.0.1
registry discovered/importable=141
core-compatible=53
optional-dependency-declared=88
formal P1 models=4
4/4 fit/predict/save-load/formal verification PASS
```

The 141-registry denominator is not 141 runtime-certified models.

### Tree GPU

- XGBoost: CUDA lane verified on exact PR source.
- CatBoost: GPU lane verified on exact PR source.
- LightGBM: resolved 4.7.0 build is **not CUDA tree learner capable**; OpenCL `device_type="gpu"` is verified and routed.

## Major active gates

Live GitHub/Linear state, not historical prose, is authoritative. Important open work includes:

| Gate | Current interpretation |
|---|---|
| #289 / TAJ-32 | Expanded v2 sktime + skforecast inventories; deterministic identities/routing still incomplete |
| #281 / TAJ-30 | TabPFN-TS-3 executable lane; current operator run blocked by invalid/expired Prior Labs token before v3 inference |
| #292 / TAJ-36 | freeze Expanded v2 count and execute full six-game runtime matrix after expansion phases |
| #297 | Toto 22M native-Linux external GPU PID/release certification |
| #265 / #266 | Broad 174×6 and Unified 250×6 runtime campaigns |
| #272 | native Windows NTFS-invalid tracked paths |
| #239 | Timer Base 84M development OOF |
| #118 | Timer-S1 PR-B runtime/certification |
| #275 | GitHub Pages activation remains blocked by repository enablement |

Open issue counts and priorities can change after this snapshot; re-fetch live GitHub/Linear before execution.

## Unified campaign state

Canonical planning/execution surface:

```bash
uv run loto3 campaign --output unused --plan-only

uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Parallel layer:

```bash
uv run python -m loto.evaluation.parallel_campaign --help
```

The campaign keeps failures/non-routable/unsupported rows visible. `matrix_complete=true` means result-row coverage, not universal runtime success or forecast superiority.

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
recent/last
frequency
statistical
```

Chronological Train / Validation / Holdout / Prospective ordering is mandatory. Scaler, encoder, feature selection and HPO must fit only inside allowed Train data. All configured seeds are retained with mean/variance/worst statistics. Predictions are sealed with SHA-256 + timestamp before the corresponding actual is read.

## What is not established

This snapshot does not establish:

- 174×6 or 250×6 universal successful execution;
- Expanded v2 source/runtime completion;
- skforecast current-main shared/provider routing completion;
- all TSFM lottery compatibility;
- all-model OOF superiority;
- Holdout or Prospective completion;
- champion selection;
- production promotion.

A valid final result may be `NO_MODEL_BEATS_BASELINE`, a documented runtime block, or no champion.
