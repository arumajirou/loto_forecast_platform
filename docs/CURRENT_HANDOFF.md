# Current Handoff

```text
status_class: AUDITED_CURRENT_STATE
audit_time: 2026-08-13T17:36+09:00
repository: arumajirou/loto_forecast_platform
documentation_audit_base_sha: 932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf
source_of_truth: live GitHub + repository code/config + retained evidence + explicitly classified operator-local evidence
```

## Start here

1. `README.md`
2. `docs/STATUS.md`
3. `docs/CURRENT_VERIFICATION_REPORT.md`
4. `docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`
5. `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`
6. `docs/CAPABILITIES_AND_OPERATIONS.md`
7. `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md`
8. `docs/PARALLEL_UNIFIED_CAMPAIGN.md`
9. `docs/CURRENT_RUNBOOK.md`
10. `docs/REQUIREMENTS.md`
11. `docs/SPECIFICATION.md`
12. `docs/ARCHITECTURE.md`
13. `docs/TEST_PLAN.md`

## Current repository boundary

Audit started from:

```text
main=932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf
latest merged PR=#308
```

The recent implementation sequence includes:

```text
#268 statistical/causal analysis foundation
#270 resource-aware runtime audit remediation
#273 observability dashboard / structured intake
#274 visual dashboard + Pages activation gate
#276 repository operations control center
#277 scheduler stabilization
#293 Expanded v2 foundation + AutoGluon expansion
#295 Toto family manifest / 22M provenance
#296 Toto 22M runtime certification infrastructure
#299 implementation-grounded README audit
#300 library/model compatibility matrix
#301 dynamic scikit-learn provider
#302 parallel Unified Campaign / live progress
#303 isotonic calibrated logistic routing
#304 XGBoost/CatBoost GPU routing
#305 LightGBM accelerator probe
#306 LightGBM OpenCL GPU routing
#307 sktime P1 normalization
#308 README reconciliation
```

## Inventory / execution surface

```text
Broad v1 = 174 identities (frozen)
Unified v1 = 250 identities
Unified model×game planning cells = 1500
Expanded v2 Phase 1 = 210 implementation identities
canonical games = 6
```

These are separate denominators. Do not silently add dynamic sklearn, sktime registry entries or future Expanded v2 entries into Broad v1.

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

## Current runtime highlights

### scikit-learn / boosting

- dynamic `loto-sklearn` provider is merged;
- Broad isotonic calibrated logistic route is implemented;
- XGBoost CUDA lane is verified on exact PR source;
- CatBoost GPU lane is verified on exact PR source;
- LightGBM OpenCL `device_type="gpu"` is verified and routed;
- resolved LightGBM build does **not** support CUDA tree learner and must remain fail-closed for `device_type="cuda"`.

### sktime

sktime 1.0.1 P1 evidence:

```text
141 discovered/importable
53 core-compatible
88 optional-dependency-declared
4 formal P1 models
4/4 fit/predict/save-load/formal verification PASS
```

Do not call all 141 runtime-certified.

### skforecast 0.23.0

A maintainer-host sequence against exact source head `9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd` produced operator-local runtime evidence for:

- recursive/direct/multi-series/statistical/backtesting/persistence surfaces;
- LightGBM/XGBoost/CatBoost estimator integration;
- RNN LSTM/GRU actual CUDA plus CPU fallback;
- Chronos-2 GPU/CPU + exog + interval;
- TimesFM 2.5 GPU/CPU + interval + quantiles;
- Moirai-2 runtime only under an unsupported dependency metadata override;
- TabICL v2 GPU/CPU + exog + interval + quantile + checkpoint SHA-256;
- TabPFN-TS adapter/device/exog construction, with inference blocked by invalid/expired Prior Labs token;
- T0 not yet executed in this sequence.

Use `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` for exact classification.

Important: this local evidence is not a substitute for #289 / TAJ-32 repository inventory/routing acceptance.

### TabICL checkpoint

```text
repo=jingang/TabICL
revision=4dcd344ece2c00be9e831fdd35bed57b5ad83e19
checkpoint=tabicl-regressor-v2-20260212.ckpt
size=114324594
sha256=0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a
status=VERIFIED
```

### TabPFN-TS current block

```text
tabpfn-time-series=1.2.0
tabpfn=8.1.0
requested_checkpoint=tabpfn-v3-regressor-v3_20260506_timeseries.ckpt
license=tabpfn-3-license-v1.0
token_valid=false
license_accepted=not evaluated
runtime inference=NOT_EXECUTED
```

The cached V2 checkpoint is a separate identity and must not be reused as V3 evidence.

### Toto 22M

PR #296 is merged, but formal runtime certification remains blocked by #297 native-Linux external process evidence.

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
```

## Current highest-value open work

### #289 / TAJ-32 — Expanded v2 sktime + skforecast

Do next:

1. re-fetch current main and pinned framework versions;
2. derive deterministic source/runtime inventories;
3. keep `algorithm_id` and `implementation_id` distinct;
4. promote scientifically meaningful skforecast strategies without wrapper×estimator Cartesian explosion;
5. preserve operator-local PASS/BLOCKED evidence as leads, not automatic current-main certification;
6. add explicit routability/capability/resource metadata;
7. add focused repository construction/predict tests;
8. retain every blocked/non-routable entry explicitly;
9. keep Broad v1=174 unchanged.

### #281 / TAJ-30 — TabPFN-TS-3

Current next action is authentication/governance, not model debugging:

1. acquire a valid Prior Labs API key without committing/logging it;
2. accept `tabpfn-3-license-v1.0` for the relevant account;
3. verify token and license acceptance directly;
4. only then download/hash the V3 checkpoint and rerun GPU/CPU inference;
5. keep V2/V3 evidence separate.

### #292 / TAJ-36 — Expanded v2 freeze/runtime matrix

Do not start the complete six-game matrix until prerequisite library expansion phases are source-complete and identity/routing metadata is stable.

### Other gates

- #297: Toto 22M native-Linux formal GPU process/release evidence;
- #265/#266: Broad/Unified complete runtime matrices;
- #272: Windows NTFS-invalid tracked paths;
- #239: Timer Base 84M development OOF;
- #118: Timer-S1 PR-B;
- #275: GitHub Pages activation.

## Scientific protocol reminders

Primary metric: **Hit@±1**.

Also retain:

- MAE / MSE / RMSE;
- position-wise Hit@±1;
- all-position Hit@±1;
- Random/fixed/mean/median/recent/frequency/statistical baselines;
- every configured seed with mean/variance/worst;
- chronological folds;
- Train-only preprocessing/HPO;
- prediction SHA-256 + timestamp before actual reads.

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

Holdout and Prospective are currently **CLOSED**.

## Before next GitHub mutation

1. re-fetch main/head/base;
2. confirm duplicate branch/PR/issue state;
3. compare exact changed files;
4. preserve expected-head SHA for merge;
5. inspect Actions/review threads;
6. never report queued/cancelled CI as PASS;
7. merge only after evidence supports the requested scope.

## Safe conclusions

A valid outcome may be:

```text
NO_MODEL_BEATS_BASELINE
BLOCKED_DEPENDENCY
BLOCKED_AUTH_OR_LICENSE
NOT_ROUTABLE
UNSUPPORTED_GAME
champion=null
```

Those are evidence outcomes, not project failures.
