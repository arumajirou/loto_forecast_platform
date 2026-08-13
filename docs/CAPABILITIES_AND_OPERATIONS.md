# Capabilities and Operations Reference

```text
status_class: LIVE_REFERENCE
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 063120fd9b07d07548442edbce480a6d068f9f43
as_of: 2026-08-13T18:04+09:00
```

## Canonical counts

```text
Broad v1=174
Probabilistic v1=76 effective
Unified v1=250 (combined conceptual denominator)
Broad current `loto3 campaign` plan=174 × 6=1,044 units
Unified combined denominator × six games=250 × 6=1,500 units
Expanded v2 Phase 1=210
Expanded v2 final=not frozen
```

**Important planner boundary:** current `uv run loto3 campaign ... --plan-only` is built from the frozen Broad catalog only. It plans **174 × 6 = 1,044** model×game units; it does not automatically append the separate 76-model probabilistic catalog. The 250/1,500 numbers are the combined Unified denominator used for cross-surface accounting, not the output count of this command.

Historical probabilistic=72 references predate the four PPL-02 identities conditionally added by the current loader.

## Capability states

| State | Meaning |
|---|---|
| `REGISTERED` | source/catalog identity exists |
| `SHARED_ROUTABLE` | shared campaign can select it |
| `PROVIDER_ROUTABLE` | dedicated provider/isolated route exists |
| `RUNTIME_CERTIFIED` | actual load/input/inference/shape/finite/device evidence exists |
| `OPERATOR_LOCAL_EVIDENCE` | maintainer-host exact-source evidence, separate from current-main retained evidence |
| `LOCAL_VERIFIED` | local exact worktree success, main未反映 |
| `OOF_EVALUATED` | chronological development OOF completed |
| `HOLDOUT_EVALUATED` | explicit authorization + Holdout completed |
| `PROSPECTIVE_EVALUATED` | presealed future forecast scored after actual |

`available=true` / import success / class export alone is not runtime certification.

## Inventory and planning

```bash
# canonical games
uv run loto3 games

# frozen Broad inventory = 174
uv run loto3 catalog --counts
uv run loto3 catalog
uv run loto models list

# IMPORTANT: Broad-only plan = 174 × 6 = 1,044 units
uv run loto3 campaign --output unused --plan-only

# Expanded v2 report (separate denominator)
uv run python scripts/report_expanded_model_inventory.py

# effective probabilistic catalog = 76, separate from current Broad campaign planner
uv run loto3 probabilistic catalog-list
```

There is no claim here that a single current `loto3 campaign --plan-only` invocation produces the combined 250 × 6 = 1,500 matrix. Any combined Broad+Probabilistic orchestration must explicitly combine those surfaces and preserve their distinct execution/evidence contracts.

Dynamic sklearn:

```bash
uv run loto-sklearn list
uv run loto-sklearn smoke --model RandomForestRegressor --seed 1
uv run loto-sklearn certify --kind all --seed 1 --output artifacts/sklearn-certification
```

## Broad development campaign

The current `loto3 campaign` path is Broad-v1 based:

```bash
uv run loto3 campaign \
  --input-dir /absolute/path/to/canonical-csv-directory \
  --output /absolute/path/to/new-run-directory
```

Parallel-by-game Broad orchestration:

```bash
uv run python -m loto.evaluation.parallel_campaign run \
  --input-dir /absolute/path/to/canonical-csv-directory \
  --output artifacts/unified-campaign/parallel-$(date +%Y%m%d-%H%M%S) \
  --games mini,loto6,loto7,bingo5,numbers3,numbers4 \
  --workers 6 \
  --reserve-cpus 2 \
  --seeds 1 \
  --folds 3 \
  --test-size 20 \
  --min-train-size 100 \
  --holdout-size 50 \
  --device cpu
```

The historical/module name `Unified Campaign` must not be read as proof that the current planner silently appends the separate probabilistic catalog. Verify the actual planned rows in the emitted manifest before interpreting the denominator.

Live status:

```bash
uv run python -m loto.evaluation.parallel_campaign status \
  --root <RUN_OUTPUT> --watch --interval 2 --hardware
```

`matrix_complete=true` means all planned units have an explicit row/status, not that all succeeded.

## Scientific contract

Primary metric: **Hit@±1**.

Also report MAE/MSE/RMSE, position Hit@±1 and all-position Hit@±1. Mandatory baselines include Random/fixed/mean/median/last/frequency/statistical.

```text
Train-only preprocessing/HPO
-> chronological Validation/OOF
-> retain all seeds + mean/variance/worst
-> prediction SHA-256 seal before actual
-> explicit Holdout authorization
-> Holdout
-> sealed Prospective
-> actual arrival/scoring
-> human promotion
```

## Library execution surfaces

| Library | Main surface | Runtime/accelerator note |
|---|---|---|
| sklearn Broad | shared/Broad campaign | CPU + tree-specific GPU routes |
| sklearn dynamic | `loto-sklearn` | installed-version dependent |
| XGBoost | resource-aware Broad campaign | CUDA exact-head VERIFIED |
| CatBoost | resource-aware Broad campaign | GPU exact-head VERIFIED |
| LightGBM | resource-aware Broad campaign | OpenCL `device_type="gpu"` VERIFIED; current CUDA learner unavailable |
| StatsForecast | shared 8 + campaign | lifecycle + six-game development evidence |
| MLForecast | shared 2 + Auto | backend dependent |
| NeuralForecast fixed | shared subset + dedicated | GPU capable |
| NeuralForecast Auto | AutoModel runner | Ray/Optuna + GPU |
| AutoGluon | Broad umbrella / Expanded 37 | isolated provider |
| Darts | provider/campaign | main runtime foundation; corrected Torch local evidence main-pending |
| GluonTS | shared + isolated | Draft #309 P6 CPU-pinned 18/18 exact-head, main pending |
| sktime | isolated | P1 fixed four formal PASS |
| skforecast | repo integration pending | operator-local 0.23.0 runtime evidence |
| TSFM | provider-specific | retained 19/21 certified |
| probabilistic | separate catalog/run/API surface | effective 76; not automatically part of current Broad planner |

## Tree GPU

```text
XGBoost: GPU lease + device=cuda -> VERIFIED #304
CatBoost: GPU lease + task_type=GPU -> VERIFIED #304
LightGBM: device_type=gpu OpenCL -> VERIFIED #305/#306
LightGBM CUDA tree learner -> NOT AVAILABLE in current resolved build
```

## StatsForecast

Shared IDs:

```text
stats-naive
stats-historic-average
stats-autoarima
stats-autoets
stats-autotheta
stats-autoces
stats-croston
stats-tsb
```

Development evidence:

```text
39 primary models × 6 games = 234/234 SUCCEEDED
SklearnModel = 6 EXOGENOUS_EVALUATION_DEFERRED
NaNModel = 6 EXPECTED_NEGATIVE_CONTROL
Holdout=false
Prospective=false
```

## NeuralForecast Auto

Controls include Ray/Optuna backend, search strategy, trials, CPU/GPU resource fractions, parallelism, precision, outer seed, refit policy and model-specific overlays. PR #260/#261 repaired seed/precision propagation into actual AutoModel/search evidence.

## Darts runtime foundation

```bash
uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_notorch.yaml \
  --repository-root .

uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_torch.yaml \
  --repository-root .
```

Current main bootstrap validates project/lock/frozen sync/package/import/export/CUDA/PID/hash and creates `CAMPAIGN_APPROVAL.json` only when required checks PASS. **It does not train or predict.**

Local exact-worktree evidence, main-pending:

```text
darts=0.46.1
torch=2.9.1+cu130
CUDA=13.0
pytorch-lightning=2.6.5
RTX 5070 Ti
official bootstrap=PASS
campaign_execution_allowed=true
NLinear actual GPU fit/predict=VERIFIED
DLinear actual GPU fit/predict=VERIFIED
```

Current main `smoke_models` is not wired to actual fit/predict. The first integration patch failed with `corrupt patch at line 381`, so formal model-smoke integration is EXECUTION_PENDING.

## GluonTS current boundary

Draft #309 reports latest 9/9 + compat 9/9 = 18/18 CPU lifecycle exact-head VERIFIED with valid P7 evidence. Until merged, this is not current-main certification. GPU/OOF are out of scope.

## skforecast operator-local evidence

Detailed source: [`SKFORECAST_RUNTIME_CERTIFICATION.md`](SKFORECAST_RUNTIME_CERTIFICATION.md).

Operator-local evidence includes core recursive/direct/multi-series/multivariate surfaces, features/backtesting/Optuna/persistence/drift/intervals, RNN GPU+CPU fallback, Chronos-2, TimesFM2.5 and TabICL v2.

Key qualifiers:

```text
Moirai-2 normal dependency routability=BLOCKED
Moirai-2 runtime under unsupported override=VERIFIED
TabPFN-TS v3 inference=NOT_EXECUTED
TabPFN token/license=INVALID_OR_EXPIRED_TOKEN
```

## Runtime certification checklist

```text
exact version/revision
load/import
input contract
construct
fit or zero-shot
predict
shape + finite
device
GPU PID/UUID/VRAM
CPU fallback
save/load/re-predict when applicable
process release when applicable
artifact SHA-256
```

## Governance

```text
Holdout=CLOSED
Prospective=CLOSED
Automatic promotion=FORBIDDEN
Human approval=REQUIRED
```

Runtime/functionality and forecast skill are separate. `NO_MODEL_BEATS_BASELINE` is a valid scientific result.
