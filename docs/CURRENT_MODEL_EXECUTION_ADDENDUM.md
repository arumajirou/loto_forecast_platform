# Current Model Execution Addendum

```text
status_class: AUDITED_CURRENT_STATE
audit_time: 2026-08-13T18:10+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
```

This addendum records current execution/evaluation facts layered on top of the detailed library/model compatibility matrix. It preserves the distinction between merged code, exact-PR-source evidence and operator/local evidence.

## 1. Campaign denominator boundaries

```text
Broad v1 = 174 frozen identities
Probabilistic effective v1 = 76 identities
Combined Broad + Probabilistic accounting = 250 identities
Canonical games = 6
Current `loto3 campaign` Broad plan = 174 × 6 = 1,044 units
Combined accounting × six games = 250 × 6 = 1,500 cells
Expanded v2 Phase 1 = 210 implementation identities
```

PR #311 corrected a previously easy-to-misread boundary: current `uv run loto3 campaign --plan-only` plans the Broad catalog only. It does **not** automatically append the separate probabilistic 76 identities. Therefore 1,500 is a combined accounting denominator, not the output row count of the current single Broad campaign command.

```text
matrix_complete
!= all models routable
!= all models runtime-certified
!= all rows successful
!= OOF superiority
```

## 2. Current execution architecture

Merged runtime paths include:

- deterministic task fingerprints for resume;
- explicit physical GPU assignment;
- resource-aware CPU/GPU admission;
- process-tree timeout termination;
- outer-worker-cap enforcement;
- game-parallel Broad campaign wrapper;
- atomic progress state;
- fail-visible final rows;
- aggregate artifacts and SHA-256 manifests.

Parallel execution does not alter the scientific split/lock contract inside each worker.

## 3. scikit-learn / boosting

Merged runtime changes include:

- `loto-sklearn` dynamic provider based on installed `sklearn.utils.all_estimators()`;
- `isotonic-calibrated-logistic` routed through `CalibratedClassifierCV(method="isotonic", cv=3)`;
- XGBoost GPU lease -> GPU constructor/runtime route with bounded exact-source evidence;
- CatBoost GPU lease -> GPU constructor/runtime route with bounded exact-source evidence;
- LightGBM 4.7.0 fail-closed capability probe:
  - `device_type="cuda"`: unsupported/not certified for the resolved build;
  - `device_type="gpu"`: OpenCL runtime verified;
- LightGBM classifier/position routes use the verified OpenCL contract when a scheduler GPU lease exists.

Do not describe the resolved LightGBM build as CUDA-certified.

## 4. sktime

Current sktime 1.0.1 evidence:

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

All four passed dependency/import/construct/fit/predict/finite/save-load/re-predict/formal verification on exact source after the P1 input normalization repair.

This is not a 141-model runtime certification.

## 5. skforecast 0.23.0 operator-local evidence

The repository Broad identity remains `skforecast-recursive`, and #289 / TAJ-32 remains open for Expanded v2 inventory/routing integration.

A maintainer-host sequence against exact source head `9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd` produced bounded runtime evidence for:

- recursive/direct/multi-series/multivariate/statistical/backtesting/persistence surfaces;
- optional LightGBM/XGBoost/CatBoost recursive estimator smoke on CPU;
- RNN LSTM/GRU actual CUDA and LSTM CPU fallback;
- Chronos-2 GPU+CPU/exog/point/interval;
- TimesFM 2.5 GPU+CPU/point/interval/quantiles;
- Moirai-2 runtime only under a controlled unsupported dependency override;
- TabICL v2 GPU+CPU/exog/interval/quantile plus checkpoint identity/hash;
- TabPFN-TS V3 adapter/device/exog setup with inference blocked before checkpoint access by invalid/expired authentication;
- T0 not executed in that sequence.

Detailed evidence: `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`.

## 6. Darts current execution boundary

PR #311 updated Darts documentation/tracking. Current main contains Darts provider/campaign/runtime foundations. Expanded v2 source-complete inventory/routing remains open under #286 / TAJ-27.

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

Classification:

```text
LOCAL_VERIFIED / MAIN_PENDING
```

This bounded evidence corrects the older blanket statement `REAL_DARTS_RUNTIME_BLOCKED`, but it does not certify all 58 upstream public forecasting exports. Current-main `smoke_models` is not a universal actual fit/predict certification. See `docs/darts/CURRENT_STATE_DARTS.md`.

## 7. GluonTS Draft PR #309 exact-head evidence

The GluonTS P6/P7 CPU certification repair is not merged at this documentation base.

```text
PR=309
state=OPEN
draft=true
head=edba730a4f2c944c1ccc0bee510f7ce34833b6c3
current-main integration=false
```

Exact-head P6 replay:

```text
latest=9/9 VERIFIED
compat=9/9 VERIFIED
total=18/18 VERIFIED
observed_devices=['cpu']
CUDA devices observed=0
```

Exact-head P7D handoff/independent verification:

```text
P7D_RC=0
VERIFY_RC=0
FORMAL_RC=0
evidence_state=VALID
certification_status=VERIFIED
verification_state=VERIFIED
verified_model_lifecycles=18
p8_eligible=true
source_commit_sha=edba730a4f2c944c1ccc0bee510f7ce34833b6c3
archive_sha256=b56a94b0a0be29eff0a00960bdd9d6c0eeb3c85a13b166dce539b8dbc87b006b
```

Root causes addressed on that exact PR source include:

- removing forced `enable_checkpointing=False` that conflicted with GluonTS/Lightning callbacks;
- per-stage subprocess working directories;
- CPU-pinned provider subprocesses via CUDA visibility masking;
- uv-managed Python symlink provenance handling while enforcing isolated prefix provenance.

GitHub `ci` and `windows-portability-ci` were still queued at documentation audit time. Therefore:

```text
GLUONTS_EXACT_HEAD_CPU_RUNTIME=VERIFIED
GLUONTS_CURRENT_MAIN_RUNTIME_FROM_309=MAIN_PENDING
GLUONTS_GPU_CERTIFICATION=NOT_CLAIMED
GLUONTS_OOF=NOT_ESTABLISHED_BY_P6_P7
```

## 8. TabICL artifact identity

Operator-local TabICL checkpoint identity:

```text
repo=jingang/TabICL
revision=4dcd344ece2c00be9e831fdd35bed57b5ad83e19
checkpoint=tabicl-regressor-v2-20260212.ckpt
size_bytes=114324594
sha256=0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a
status=VERIFIED
```

## 9. TabPFN-TS current authentication boundary

```text
tabpfn-time-series=1.2.0
tabpfn=8.1.0
requested_checkpoint=tabpfn-v3-regressor-v3_20260506_timeseries.ckpt
license_name=tabpfn-3-license-v1.0
token_valid=false
license_accepted=not evaluated
runtime_inference=NOT_EXECUTED
```

This is an authentication/governance block, not a CUDA/skforecast inference failure. A cached V2 checkpoint is a different identity and is not accepted as V3 evidence.

## 10. Toto 2.0 22M current gate

PR #296 merged a pinned family/runtime certification path. Formal runtime status remains fail-closed until #297 obtains native-Linux external provider PID / VRAM / post-exit release evidence.

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
Holdout=CLOSED
Prospective=CLOSED
```

## 11. Scientific evaluation boundary

Runtime smoke and synthetic metrics do not establish forecast skill.

Formal development evaluation requires:

- Hit@±1 primary;
- MAE/MSE/RMSE;
- position-wise and all-position Hit@±1;
- Random/fixed/mean/median/last/frequency/statistical baselines;
- chronological folds;
- Train-only preprocessing/HPO;
- all configured seeds and mean/variance/worst summaries;
- prediction SHA-256 + timestamp before actual read.

Current gates:

```text
Holdout=CLOSED
Prospective=CLOSED
automatic_promotion=FORBIDDEN
```

## 12. Source-of-truth order

Use evidence in this order:

1. current repository code/config;
2. tests/workflows/repository-retained artifacts;
3. exact-PR-source evidence tied to an immutable SHA;
4. exact-source operator/local runtime evidence;
5. merged PR/commit history;
6. live GitHub/Linear gate state;
7. current documentation;
8. historical snapshots.

An exact-source local or PR-head PASS does not automatically certify a newer/current main SHA.
