# skforecast Runtime Certification Status

```text
status_class: OPERATOR_LOCAL_EVIDENCE_SNAPSHOT
as_of: 2026-08-13
repository: arumajirou/loto_forecast_platform
documentation_audit_base: 932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf
operator_runtime_source_head: 9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd
skforecast: 0.23.0
python: 3.13.13
torch: 2.9.1
primary_gpu: NVIDIA GeForce RTX 5070 Ti
```

## Purpose

This document records the skforecast 0.23.0 runtime evidence collected on the maintainer host after the repository documentation audit in PR #308.

The evidence class is deliberately **operator-local**. It was produced outside repository-retained GitHub Actions artifacts and against source head `9fcc127...`, not against the current merged `main` SHA. Therefore this document does **not** silently upgrade repository routing, Expanded v2 inventory completion, OOF status, Holdout, Prospective, or promotion state.

Reading rule:

```text
library runtime evidence
!= repository shared/provider routability
!= Expanded v2 inventory completion
!= six-game OOF evaluation
!= Holdout/Prospective success
!= promotion eligibility
```

## 1. Core skforecast surface

After correcting two smoke-harness assumptions, no genuine core runtime failure remained in the tested surface.

| Surface | Tested implementation | Result | Boundary |
|---|---|---|---|
| recursive ML | `ForecasterRecursive + Ridge` with exog | **PASS** | synthetic runtime smoke |
| recursive ML | `ForecasterRecursive + HistGradientBoostingRegressor` | **PASS** | synthetic runtime smoke |
| direct ML | `ForecasterDirect + Ridge` | **PASS** | synthetic runtime smoke |
| multi-series | `ForecasterRecursiveMultiSeries + Ridge` | **PASS** | expected long output = levels × steps |
| multivariate direct | `ForecasterDirectMultiVariate + Ridge` | **PASS** | synthetic runtime smoke |
| baseline | `ForecasterEquivalentDate` | **PASS** | baseline/runtime only |
| features | `RollingFeatures + CalendarFeatures` | **PASS** | feature construction |
| backtesting | `TimeSeriesFold + backtesting_forecaster` | **PASS** | synthetic Hit@±1/MAE/RMSE only |
| HPO | Optuna Bayesian search | **PASS** | 2-trial smoke, not tuned production result |
| statistical wrapper | `ForecasterStats + ARAR` | **PASS** | runtime smoke |
| persistence | `save_forecaster` / `load_forecaster` | **PASS** | exact round-trip prediction equality |
| drift | `RangeDriftDetector` | **PASS** | runtime smoke |
| interval | in-sample bootstrap | **PASS** | required residual storage enabled |
| interval | out-of-sample calibration | **PASS WITH WARNING** | sparse residual bins required fallback sampling |

Initial smoke failures for `ForecasterRecursiveMultiSeries` output length and bootstrap interval residual storage were test-harness/configuration errors, not skforecast runtime defects.

## 2. Optional estimator integrations

`ForecasterRecursive` construction and finite prediction were exercised with common tree/boosting estimators.

| Estimator | Device in this smoke | Result | Smoke-only Hit@±1 |
|---|---|---|---:|
| LightGBM 4.7.0 | CPU | **PASS** | 1.0 |
| XGBoost 3.2.0 | CPU | **PASS** | 1.0 |
| CatBoost 1.2.10 | CPU | **PASS** | 1.0 |

These five-point synthetic metrics are diagnostics only. They are not Loto development OOF, Holdout, Prospective, superiority, or promotion evidence.

## 3. `ForecasterRnn`

### GPU

| Configuration | Result | Device evidence |
|---|---|---|
| LSTM / Keras torch backend | **VERIFIED** | model variables `cuda:0`, positive PyTorch peak allocation, matching `nvidia-smi` PID |
| GRU / Keras torch backend | **VERIFIED** | model variables `cuda:0`, positive PyTorch peak allocation, matching `nvidia-smi` PID |

Observed peak PyTorch allocation was about 26 MB and the process was externally visible at about 410–412 MiB in `nvidia-smi`.

### CPU fallback

`ForecasterRnn + LSTM` was rerun with CUDA hidden. Torch reported zero visible CUDA devices, Keras used CPU, model variables were on CPU, and CUDA allocation remained zero. Result: **VERIFIED**.

Non-fatal warnings remain for Keras optimizer-state loading and torch-RNN contiguous-memory performance. Strict optimizer-state checkpoint-resume semantics are not certified by this smoke.

## 4. Foundation adapters

### 4.1 Chronos-2

Test identity: `autogluon/chronos-2-small`.

| Capability | GPU | CPU fallback |
|---|---:|---:|
| adapter construction | PASS | PASS |
| `Chronos2Pipeline` load | PASS | PASS |
| known future exog | PASS | PASS |
| point prediction | PASS | PASS |
| native interval | PASS | PASS |
| finite output / expected shape | PASS | PASS |
| actual CUDA use | PASS | n/a |
| zero CUDA allocation | n/a | PASS |

Observed Hugging Face revision during the run: `ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a`.

The revision was observed, not enforced through a repository runtime contract, so exact checkpoint-revision pinning remains a separate certification gate.

### 4.2 TimesFM 2.5

Test identity: `google/timesfm-2.5-200m-pytorch`.

- skforecast adapter: `TimesFMAdapter`
- exogenous variables: correctly **not supported** by this adapter
- point prediction: PASS
- native interval: PASS
- q0.1/q0.5/q0.9: PASS
- GPU: PASS with positive CUDA allocation and matching external PID
- CPU fallback: PASS with zero CUDA allocation
- GPU/CPU output: effectively identical at floating-point tolerance

TimesFM source revision used by the operator lane: `3dae50b20d7a724981e8ea36cda75578f80dd2dc`.

Observed model Hub revision: `1d952420fba87f3c6dee4f240de0f1a0fbc790e3`.

The package metadata version and the model generation name are separate identities; model checkpoint revision enforcement remains a distinct gate.

### 4.3 Moirai-2

Test identity: `Salesforce/moirai-2.0-R-small`.

Normal dependency resolution is **BLOCKED** because the declared dependency sets do not intersect cleanly with the skforecast 0.23.0/root runtime lane. The observed conflicts included:

- skforecast requires SciPy in the `>=1.12` range while `uni2ts==2.0.0` declares `scipy~=1.11.3`;
- the maintained CUDA lane uses Torch 2.9.1 while `uni2ts==2.0.0` declares `torch<2.5`.

A deliberately isolated compatibility probe installed `uni2ts==2.0.0` without allowing its metadata to replace the controlled stack. Under that **unsupported metadata override**:

- `MoiraiAdapter` imported;
- GPU point/interval/quantile inference passed;
- CPU fallback point/interval/quantile inference passed;
- finite/shape checks passed;
- device evidence passed.

Correct status:

```text
runtime_under_override = VERIFIED
normal_dependency_routability = BLOCKED
formal_repository_runtime_certification = NOT_ESTABLISHED
```

Do not label this implementation generally routable until the dependency contract is resolved or a reviewed isolated environment is formalized.

### 4.4 TabICL v2

Test package: `tabicl==2.1.1`.

Tested with `TabICLAdapter` / native `TabICLForecaster` using known-future exogenous variables.

| Capability | GPU | CPU fallback |
|---|---:|---:|
| adapter/model construction | PASS | PASS |
| exogenous variables | PASS | PASS |
| point prediction | PASS | PASS |
| prediction interval | PASS | PASS |
| q0.1/q0.5/q0.9 | PASS | PASS |
| finite/shape checks | PASS | PASS |
| actual CUDA allocation / external PID | PASS | n/a |
| zero CUDA allocation | n/a | PASS |

GPU/CPU maximum point-prediction difference: `3.814697265625e-06`.

Checkpoint identity was independently resolved through `huggingface_hub`:

```text
repo = jingang/TabICL
repo_revision = 4dcd344ece2c00be9e831fdd35bed57b5ad83e19
filename = tabicl-regressor-v2-20260212.ckpt
size_bytes = 114324594
sha256 = 0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a
checkpoint_status = VERIFIED
```

This is the strongest skforecast foundation evidence in the operator-local set because both runtime and checkpoint bytes were verified.

### 4.5 TabPFN-TS

Test packages:

```text
tabpfn-time-series = 1.2.0
tabpfn = 8.1.0
model_id = priorlabs/tabpfn-ts
mode = local
```

The following succeeded before model-weight access:

- dependency resolution;
- import;
- `TabPFNAdapter` construction;
- `allow_exog=True` contract;
- GPU visibility;
- CPU fallback setup.

Inference did **not** execute. Weight download stopped at the Prior Labs license/authentication gate. A direct authentication diagnostic established:

```text
license_name = tabpfn-3-license-v1.0
token_valid = false
license_accepted = not evaluated
status = INVALID_OR_EXPIRED_TOKEN
```

The requested v3 time-series checkpoint was identified as:

```text
tabpfn-v3-regressor-v3_20260506_timeseries.ckpt
```

Only its lock file was created; the v3 weight bytes were not downloaded. A previously cached `TabPFN-v2-reg` checkpoint is a different identity and must not be reused as v3 evidence.

Correct status:

```text
adapter_contract = VERIFIED
runtime_inference = NOT_EXECUTED
checkpoint = NOT_ACQUIRED
blocker = INVALID_OR_EXPIRED_TOKEN / LICENSE_AUTH
```

### 4.6 T0

No new operator-local skforecast T0 execution was completed in this evidence sequence. It remains **EXECUTION_PENDING** for this skforecast-specific certification track.

## 5. Repository integration boundary

The root repository currently represents skforecast in Broad v1 as one frozen identity:

```text
skforecast-recursive
```

The optional dependency declaration in `pyproject.toml` is framework-level (`skforecast>=0.17`). The operator smoke used the locked/runtime-resolved skforecast 0.23.0 environment.

GitHub Issue #289 / Linear TAJ-32 remains the authoritative implementation task for Expanded v2 sktime + skforecast inventories. This operator evidence materially reduces uncertainty about the upstream skforecast runtime surface, but it does **not** by itself satisfy #289 acceptance criteria for:

- deterministic Expanded v2 identity count;
- `algorithm_id` vs `implementation_id` catalog integration;
- repository routability metadata;
- source/revision hashes for every expanded implementation;
- no-silent-skip inventory execution;
- six-game runtime/functionality matrix.

## 6. Recommended Expanded v2 classification

Do not create a Cartesian product of every skforecast wrapper × every estimator. Prefer scientifically meaningful implementation identities.

Suggested grouping:

| algorithm / strategy | example implementation identity | current operator evidence |
|---|---|---|
| recursive regression | `skforecast-recursive-ridge` | PASS |
| recursive tree boosting | `skforecast-recursive-histgb` | PASS |
| recursive external boosters | LightGBM / XGBoost / CatBoost variants | PASS on CPU smoke |
| direct regression | `skforecast-direct-ridge` | PASS |
| recursive multiseries | `skforecast-recursive-multiseries-ridge` | PASS |
| direct multivariate | `skforecast-direct-multivariate-ridge` | PASS |
| equivalent-date baseline | `skforecast-equivalent-date` | PASS |
| stats ARAR | `skforecast-stats-arar` | PASS |
| RNN LSTM / GRU | `skforecast-rnn-*` | GPU + CPU fallback PASS |
| Foundation Chronos-2 | `skforecast-foundation-chronos2-small` | GPU + CPU PASS |
| Foundation TimesFM 2.5 | `skforecast-foundation-timesfm25` | GPU + CPU PASS |
| Foundation Moirai-2 | `skforecast-foundation-moirai2` | runtime PASS only under unsupported dependency override |
| Foundation TabICL v2 | `skforecast-foundation-tabicl-v2` | GPU + CPU + checkpoint SHA PASS |
| Foundation TabPFN-TS | `skforecast-foundation-tabpfn-ts3` | adapter PASS; auth/license blocked before inference |
| Foundation T0 | `skforecast-foundation-t0` | not executed in this sequence |

This table is an implementation-planning aid, not a committed Expanded v2 count.

## 7. Scientific boundary

All metrics emitted by these smoke tests are synthetic runtime diagnostics.

They do not establish:

- real six-game development OOF quality;
- superiority over Random/fixed/mean/median/recent/frequency/statistical baselines;
- multi-seed mean/variance/worst performance;
- Holdout success;
- Prospective success;
- promotion eligibility;
- a champion.

Holdout remains **CLOSED**. Prospective remains **CLOSED**. Automatic promotion remains **FORBIDDEN**.
