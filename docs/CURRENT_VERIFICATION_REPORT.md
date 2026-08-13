# Current Verification Report

```text
status_class: AUDITED_CURRENT_STATE
audit_time: 2026-08-13T17:36+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf
scope: current merged implementation + retained evidence + explicitly separated operator-local runtime evidence
```

## Verdict

```text
SIX_GAME_GEOMETRY=VERIFIED
BROAD_V1_174=FROZEN
UNIFIED_V1_250=PLANNED_AND_ROUTABLE_BY_EXPLICIT_STATUS
PARALLEL_UNIFIED_CAMPAIGN=IMPLEMENTED
SCIKIT_LEARN_DYNAMIC_PROVIDER=IMPLEMENTED
XGBOOST_GPU_ROUTE=VERIFIED_ON_EXACT_PR_SOURCE
CATBOOST_GPU_ROUTE=VERIFIED_ON_EXACT_PR_SOURCE
LIGHTGBM_OPENCL_GPU_ROUTE=VERIFIED_ON_EXACT_PR_SOURCE
LIGHTGBM_CUDA=NOT_CERTIFIED
SKTIME_P1_FIXED_4=VERIFIED_ON_EXACT_PR_SOURCE
SKFORECAST_0_23_OPERATOR_RUNTIME=PARTIALLY_VERIFIED
SKFORECAST_EXPANDED_V2_REPOSITORY_INTEGRATION=OPEN
HOLDOUT=CLOSED
PROSPECTIVE=CLOSED
AUTOMATIC_PROMOTION=FORBIDDEN
CHAMPION=NOT_AUTHORIZED
```

## Evidence classes

This report intentionally separates evidence classes.

| class | meaning |
|---|---|
| `CURRENT_CODE` | behavior visible in current repository code/config |
| `REPOSITORY_RETAINED` | tests/workflows/artifacts committed or retained through repository/GitHub evidence |
| `EXACT_PR_SOURCE` | exact-head worktree/CI/runtime evidence for a specific PR SHA |
| `OPERATOR_LOCAL` | maintainer-host runtime evidence for an exact source SHA, not automatically current-main certification |
| `SCIENTIFIC_EVALUATION` | chronological development OOF / Holdout / Prospective evidence |

Evidence from one class is not silently promoted into another.

## Recent merged sequence

| PR | Merge SHA | Verification / implementation boundary |
|---|---|---|
| #268 | `81bd4f8123d2a72226347c1cd2220fe95a17d750` | statistical/causal analysis foundation; development-only claim boundary |
| #270 | `775274cc22cf6701f148da80dfe86cb1bd099a7e` | runtime evidence serialization + resource-aware broad runner |
| #273 | `522253eab194b81a8d804236d5477a4bd9bacd68` | repository observability dashboard / structured intake |
| #274 | `c57731e17b43f8f5d9e038c75017aa9ce83fd5e9` | evidence-aware visual dashboard; Pages activation remains separate |
| #276 | `4eabd68d422baefe5180c747bb4bdc83df1caba2` | operations control center / workflow classification |
| #277 | `1df090fa34fbf1d32ec7000b25689c49e0c20074` | resume fingerprint, physical GPU assignment, process-tree cleanup, outer worker cap |
| #293 | `f04cd876f61b3c2ef85529082a6ba812f7859f6f` | Expanded v2 foundation + AutoGluon 37 implementation identities |
| #295 | `951f5f57d8e975bd9b1dbf41a213569733a340e4` | Toto family manifest + 22M provenance gate |
| #296 | `abe7e02cdfc900618c83b21c922b4fd3f078b036` | Toto 22M runtime/certification infrastructure; formal native-Linux gate remains open |
| #299 | `05eba49dad8c0700c303783267784cfde081e419` | implementation-grounded README audit |
| #300 | `a7eb50ca534c4880681d5febab193b0c2692f50c` | library/model compatibility matrix |
| #301 | `3cc73dbad8c437bc5b8c18b20d00fb59ba60522d` | dynamic scikit-learn all-estimator provider |
| #302 | `7d75dadc8c9da6292988ad7b4691e020dc90cc1e` | process-parallel Unified Campaign and live progress |
| #303 | `b9be417463395642521a9955b055fdeac5aa1f8d` | isotonic calibrated logistic factory/routing repair |
| #304 | `de1444af8915c69e466c0ded16c972e7dbabff0f` | XGBoost/CatBoost GPU lease → constructor routing |
| #305 | `a03053eabf838d0e9583b49aac1aa3c2f40de6b0` | fail-closed LightGBM accelerator probe |
| #306 | `feb4ea5ec6c63c1e3ceab26bcf9d3bc731d14add` | LightGBM OpenCL GPU routing |
| #307 | `ed7d6c8151254653d44296b608457200ac80c5ce` | sktime P1 numeric input-contract normalization |
| #308 | `932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf` | current-state README reconciliation |

## Current code-grounded capability boundary

Current repository code and merged history establish at least:

- canonical six-game geometry;
- frozen Broad v1 174 identity inventory;
- Unified v1 250 planning inventory;
- Expanded v2 Phase 1 = 210 identities;
- shared candidate/position/foundation routing surfaces;
- separate provider/isolated execution surfaces;
- resource-aware scheduler with explicit GPU assignment and process cleanup;
- game-parallel Unified Campaign with progress and aggregate artifacts;
- dynamic scikit-learn provider;
- GPU-routed XGBoost/CatBoost and OpenCL-routed LightGBM;
- StatsForecast/MLForecast/NeuralForecast/AutoNF/AutoGluon/sktime/TSFM implementation surfaces;
- geometry-general Hit@±1/MAE/MSE/RMSE evaluation;
- prediction sealing before actual scoring reads in the unified development path;
- theory-aware promotion eligibility with manual-only promotion policy;
- paired-score MDE/power planning;
- statistical/causal exploratory foundation with fail-closed causal eligibility.

## sktime evidence boundary

Exact PR-source evidence for sktime 1.0.1 P1 records:

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
exact re-prediction equality = PASS
artifact verification = PASS
```

This does not certify all 141 forecasters. Expanded v2 source/routing work remains tracked under #289 / TAJ-32.

## skforecast operator-local runtime evidence

A dedicated maintainer-host sequence exercised skforecast 0.23.0 against exact source head:

```text
9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd
```

The tests are documented in `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`.

### Core / wrappers

After correcting two harness/config assumptions, tested core surfaces completed without a genuine skforecast runtime failure:

- ForecasterRecursive + Ridge/exog;
- ForecasterRecursive + HistGradientBoosting;
- ForecasterDirect + Ridge;
- ForecasterRecursiveMultiSeries;
- ForecasterDirectMultiVariate;
- ForecasterEquivalentDate;
- ForecasterStats + ARAR;
- RollingFeatures / CalendarFeatures;
- TimeSeriesFold / backtesting;
- Optuna Bayesian search;
- save/load round-trip;
- RangeDriftDetector;
- in-sample and out-of-sample interval paths.

### RNN

- LSTM / Keras torch backend: actual CUDA PASS;
- GRU / Keras torch backend: actual CUDA PASS;
- LSTM CPU fallback: PASS with zero CUDA allocation.

Device claims were backed by model variable placement, PyTorch allocation and external `nvidia-smi` PID evidence.

### Foundation adapters

| identity | operator result | certification boundary |
|---|---|---|
| `autogluon/chronos-2-small` | GPU+CPU point/interval/exog PASS | Hub revision observed, repository pin/routing separate |
| `google/timesfm-2.5-200m-pytorch` | GPU+CPU point/interval/quantile PASS | source revision recorded; checkpoint revision enforcement separate |
| `Salesforce/moirai-2.0-R-small` | GPU+CPU runtime PASS only under controlled dependency override | normal dependency routability BLOCKED |
| TabICL 2.1.1 | GPU+CPU/exog/interval/quantile PASS | checkpoint revision + local SHA-256 VERIFIED |
| TabPFN-TS 1.2.0 / TabPFN 8.1.0 | adapter/exog/device setup PASS | v3 inference NOT EXECUTED; invalid/expired token blocks weight access |
| T0 | not executed | pending |

Strongest TabICL artifact identity:

```text
repo=jingang/TabICL
revision=4dcd344ece2c00be9e831fdd35bed57b5ad83e19
checkpoint=tabicl-regressor-v2-20260212.ckpt
size_bytes=114324594
sha256=0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a
```

TabPFN-TS current diagnostic:

```text
requested_checkpoint=tabpfn-v3-regressor-v3_20260506_timeseries.ckpt
license_name=tabpfn-3-license-v1.0
token_valid=false
license_accepted=not evaluated
inference=NOT_EXECUTED
```

The cached v2 TabPFN regressor checkpoint is a different identity and is not accepted as v3 evidence.

### Repository interpretation

This local evidence materially informs #289 / TAJ-32, but the repository still needs:

- deterministic skforecast Expanded v2 identities;
- explicit `algorithm_id` vs `implementation_id`;
- repository routability/capability metadata;
- source/revision records for committed identities;
- focused repository tests;
- no-silent-skip execution;
- six-game functionality certification.

Therefore:

```text
SKFORECAST_OPERATOR_RUNTIME=PARTIALLY_VERIFIED
SKFORECAST_CURRENT_MAIN_EXPANDED_V2=NOT_COMPLETE
```

## Tree GPU verification boundary

- XGBoost: GPU lease and CUDA constructor execution verified on exact PR #304 source.
- CatBoost: GPU lease and GPU constructor execution verified on exact PR #304 source.
- LightGBM 4.7.0 resolved build: CUDA tree learner rejected by the build; OpenCL `device_type="gpu"` classifier/regressor execution and external GPU activity verified in #305; classifier/position routing through that OpenCL contract verified in #306.

No documentation should state generic “LightGBM CUDA supported” for the resolved build.

## Toto 22M boundary

Merged PR #296 has pinned snapshot/load/inference/replay evidence, but formal runtime certification remains fail-closed pending #297 native-Linux external provider-PID / per-process VRAM / post-exit release evidence.

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
Holdout=CLOSED
Prospective=CLOSED
```

## Active verification gates

Important open gates include:

- #289 / TAJ-32 — sktime + skforecast Expanded v2 inventories;
- #281 / TAJ-30 — TabPFN-TS-3 executable lane / license-auth gate;
- #292 / TAJ-36 — Expanded v2 freeze + complete six-game runtime certification;
- #297 — Toto 22M native-Linux formal GPU process/release evidence;
- #265 / #266 — Broad and Unified runtime matrices;
- #272 — native Windows path portability;
- #239 — Timer Base 84M OOF;
- #118 — Timer-S1 PR-B.

## Scientific boundary

This report does **not** certify:

- complete 174×6 / 250×6 real-data success;
- complete Expanded v2 runtime success;
- skforecast current-main routing completion;
- universal model GPU success;
- all-model development OOF superiority;
- Holdout success;
- Prospective success;
- champion selection;
- production promotion.

Synthetic smoke Hit@±1/MAE/MSE/RMSE values are runtime diagnostics only and are never substituted for Loto development OOF evidence.

Historical root `VERIFICATION_REPORT.md` remains historical evidence. Use this current file plus `docs/STATUS.md` for the live documentation snapshot.
