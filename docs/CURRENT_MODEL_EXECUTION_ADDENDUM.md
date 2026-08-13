# Current Model Execution Addendum

```text
status_class: AUDITED_CURRENT_STATE
audit_time: 2026-08-13T17:36+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf
```

This addendum records execution/evaluation changes layered on top of the detailed library/model and execution matrices. Historical runtime artifacts are not rewritten.

## 1. Canonical campaign boundaries

```text
Broad v1 = 174 frozen identities
Unified v1 = 250 canonical identities
Canonical games = 6
Unified planning matrix = 1500 units
Expanded v2 Phase 1 = 210 implementation identities
```

`uv run loto3 campaign` remains the canonical broad/unified development comparison surface, while `loto.evaluation.parallel_campaign` adds game-level process parallelism without changing the scientific split/lock semantics inside each game worker.

Coverage and success remain distinct:

```text
matrix_complete
!= all models routable
!= all models runtime-certified
!= all rows successful
!= OOF superiority
```

## 2. Current execution architecture

The current runtime path includes:

- deterministic task fingerprints for safe resume;
- explicit physical GPU assignment through `CUDA_VISIBLE_DEVICES`;
- weighted/resource-aware CPU/GPU admission;
- process-tree termination on timeout;
- shared outer-worker-cap enforcement;
- game-parallel Unified Campaign;
- atomically written progress state;
- fail-visible final statuses;
- aggregate artifacts and SHA-256 manifests.

## 3. scikit-learn / boosting update

Merged runtime changes now include:

- `loto-sklearn` dynamic provider based on installed `sklearn.utils.all_estimators()`;
- `isotonic-calibrated-logistic` routed through `CalibratedClassifierCV(method="isotonic", cv=3)`;
- XGBoost GPU lease → CUDA constructor routing verified on exact PR source;
- CatBoost GPU lease → GPU constructor routing verified on exact PR source;
- LightGBM resolved 4.7.0 build probed fail-closed:
  - `device_type="cuda"`: unsupported by this build;
  - `device_type="gpu"`: OpenCL runtime verified;
- LightGBM classifier/position Broad routes now use the certified OpenCL GPU contract when a scheduler GPU lease exists.

Do not describe the resolved LightGBM build as CUDA-certified.

## 4. sktime update

The current sktime isolated lane uses sktime 1.0.1 evidence with:

```text
141 discovered/importable
53 core compatible
88 optional dependency declared
```

Formal P1 fixed matrix:

```text
NaiveForecaster(last)
PolynomialTrendForecaster(degree=1)
ExponentialSmoothing
ThetaForecaster
```

All four passed dependency/import/construct/fit/predict/finite/save-load/re-predict/formal verification on the exact PR source after PR #307 normalized the canonical numeric input representation.

This is not a 141-model runtime certification.

## 5. skforecast 0.23.0 operator-local evidence

The repository Broad identity remains `skforecast-recursive`, and #289 / TAJ-32 remains open for Expanded v2 inventory/routing integration.

Separately, the maintainer host exercised skforecast 0.23.0 against exact source head `9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd`.

### Core strategies

Verified in synthetic runtime smoke after correcting harness/config assumptions:

- `ForecasterRecursive + Ridge + exog`;
- `ForecasterRecursive + HistGradientBoostingRegressor`;
- `ForecasterDirect + Ridge`;
- `ForecasterRecursiveMultiSeries`;
- `ForecasterDirectMultiVariate + Ridge`;
- `ForecasterEquivalentDate`;
- `ForecasterStats + ARAR`;
- Rolling/Calendar features;
- TimeSeriesFold/backtesting;
- Optuna search;
- save/load exact round trip;
- RangeDriftDetector;
- bootstrap and calibrated interval paths.

Optional recursive estimator smoke also passed with LightGBM, XGBoost and CatBoost on CPU.

### RNN

`ForecasterRnn` evidence includes:

- LSTM GPU PASS;
- GRU GPU PASS;
- LSTM CPU fallback PASS;
- actual CUDA device/model-variable/PyTorch allocation/external PID evidence;
- zero CUDA allocation in CPU fallback.

### Foundation adapters

| identity | operator-local status | boundary |
|---|---|---|
| Chronos-2 small | **GPU + CPU PASS** | exog/point/interval; Hub revision observed |
| TimesFM 2.5 | **GPU + CPU PASS** | point/interval/quantiles; exog unsupported by adapter |
| Moirai-2 small | **PASS under compatibility override** | normal dependency resolution/routability BLOCKED |
| TabICL v2 | **GPU + CPU PASS** | exog/point/interval/quantiles + checkpoint SHA verified |
| TabPFN-TS v3 path | **adapter setup PASS / inference BLOCKED** | invalid/expired Prior Labs token before weight download |
| T0 | **NOT RUN** | pending |

Detailed evidence: `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`.

## 6. TabICL artifact identity

The checkpoint used by the operator-local TabICL run was independently resolved and hashed:

```text
repo=jingang/TabICL
revision=4dcd344ece2c00be9e831fdd35bed57b5ad83e19
checkpoint=tabicl-regressor-v2-20260212.ckpt
size_bytes=114324594
sha256=0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a
status=VERIFIED
```

## 7. TabPFN-TS current authentication boundary

Current operator diagnostic:

```text
tabpfn-time-series=1.2.0
tabpfn=8.1.0
requested_checkpoint=tabpfn-v3-regressor-v3_20260506_timeseries.ckpt
license_name=tabpfn-3-license-v1.0
token_valid=false
license_accepted=not evaluated
runtime_inference=NOT_EXECUTED
```

This is an authentication/governance block, not a CUDA/skforecast inference failure. The cached TabPFN V2 regressor checkpoint is a different identity and must not be used as V3 evidence.

## 8. Toto 2.0 22M current gate

PR #296 merged a pinned family/runtime certification path. Formal runtime status still remains fail-closed until #297 obtains native-Linux external provider-PID/VRAM/release evidence.

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
Holdout=CLOSED
Prospective=CLOSED
```

## 9. Scientific evaluation boundary

Runtime smoke and synthetic metrics do not establish forecast skill.

Formal development evaluation requires:

- Hit@±1 primary;
- MAE/MSE/RMSE;
- position-wise and all-position Hit@±1;
- Random/fixed/mean/median/recent/frequency/statistical baselines;
- chronological folds;
- Train-only preprocessing/HPO;
- all configured seeds and mean/variance/worst summaries;
- prediction SHA-256 + timestamp before actual read.

Current Holdout and Prospective state:

```text
Holdout=CLOSED
Prospective=CLOSED
automatic_promotion=FORBIDDEN
```

## 10. Source-of-truth order

Use current evidence in this order:

1. repository code/config;
2. tests/workflows/repository-retained artifacts;
3. exact-source operator/local runtime evidence;
4. merged PR/commit history;
5. live GitHub/Linear gate state;
6. current documentation;
7. historical snapshots.

An exact-source local PASS does not automatically certify a newer main SHA.
