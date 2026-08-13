# Darts Current State

```text
status: PARTIALLY_VERIFIED / MAIN_RUNTIME_FOUNDATION + LOCAL_TORCH_RUNTIME_VERIFIED / EXPANDED_V2_IN_PROGRESS
main_audit_base: 063120fd9b07d07548442edbce480a6d068f9f43
main_target: darts==0.46.1
tracking: GitHub #286 / Linear TAJ-27
Holdout: CLOSED
Prospective: CLOSED
```

この文書は古い「REAL_DARTS_RUNTIME_BLOCKED」記述を置き換え、**current mainで実装済みのDarts foundation**と、**2026-08-13 local exact-worktreeで追加検証されたruntime evidence**を分離します。

## Current main foundation

### Source discovery

- Darts target: `0.46.1`;
- versioned public forecasting export fixture: **58 names**;
- deterministic discovery;
- abstract/import/non-class/alias/signature/capability metadata;
- optional dependency failures remain visible.

58 public exportsは58 standalone forecasting algorithmsではありません。base/abstract/alias/classifier/wrapper/ensemble/conformal/optional exportsを含むため、#286でsource-complete implementation classificationが必要です。

### Implemented execution surfaces

- strict request/response contracts;
- `discover` / `fit_predict` provider modes;
- local/statistical matrix;
- regression/boosting matrix;
- Torch matrix;
- foundation matrix;
- ensemble/conformal matrix;
- persistence/save-load contracts;
- chronological OOF and multi-seed summaries;
- Hit@±1-first evaluation + baselines;
- prediction seal support;
- isolated notorch / torch runtime projects;
- fail-closed runtime preflight/bootstrap.

Explicit represented groups include:

```text
Local/statistical:
NaiveMean NaiveSeasonal NaiveDrift NaiveMovingAverage ARIMA AutoARIMA
ExponentialSmoothing Theta Croston

Regression:
LinearRegressionModel RandomForestModel LightGBMModel XGBModel CatBoostModel SKLearnModel

Torch:
NBEATSModel NHiTSModel TCNModel TFTModel DLinearModel NLinearModel
TiDEModel TSMixerModel TransformerModel RNNModel

Foundation:
Chronos2Model TimesFM2p5Model TiRexModel PatchTSTFMModel

Ensemble/conformal:
NaiveEnsembleModel RegressionEnsembleModel ConformalNaiveModel ConformalQRModel
```

These explicit matrices are not the final source-complete identity set.

## Current main runtime bootstrap

```bash
uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_notorch.yaml \
  --repository-root .

uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_torch.yaml \
  --repository-root .
```

Bootstrap validates repository-relative paths, resolves `uv`, locks the selected isolated project, hashes `uv.lock`, performs frozen sync, runs preflight, validates report/lock hashes and creates `CAMPAIGN_APPROVAL.json` only when all required stages PASS.

**Current bootstrap does not train or predict.**

Current `run_runtime_preflight()` verifies:

- Python version range;
- lockfile existence/SHA;
- exact package versions;
- required/optional imports;
- required Darts exports;
- CUDA availability/allocation/synchronization;
- CUDA device information;
- `nvidia-smi` PID evidence;
- tamper-sensitive report hash.

Important implementation gap: `RuntimeProfile` declares `smoke_models`, but current main `run_runtime_preflight()` does not execute model construct/fit/predict from that field.

## 2026-08-13 local Torch correction — MAIN PENDING

Local exact-worktree investigation found two runtime-contract mismatches:

1. `darts[torch]==0.46.1` permits `torch>=2.0.0`; without explicit isolated pin, actual resolution can drift from the preflight's intended Torch runtime.
2. upstream Darts uses `pytorch-lightning`; the import is `pytorch_lightning`, while current main profile requests `lightning`.

Locally verified corrective runtime:

```text
darts=0.46.1
torch=2.9.1+cu130
torch CUDA=13.0
pytorch-lightning=2.6.5
Python=3.13
GPU=NVIDIA GeForce RTX 5070 Ti
```

Isolated lock SHA-256:

```text
41d0bed42194b6f4d79f6ee027a4a716230fedfa18a34c2830091d64ef3bc4e9
```

These dependency/profile/lock changes are not current main until a separate code PR is merged.

## Local official bootstrap evidence

```text
DARTS_TORCH_ENV=VERIFIED
focused test_runtime_preflight=12/12 PASS
overall_status=PASS
preflight_status=PASS
approval_created=true
campaign_execution_allowed=true
BOOTSTRAP_RC=0
```

Hash chain:

```text
lock=41d0bed42194b6f4d79f6ee027a4a716230fedfa18a34c2830091d64ef3bc4e9
preflight=6fd6e52c45556030503b9f8a4b980c6e55c63e9d1bcb371ca70a809a717ed0fd
bootstrap=e3b8c2dc29ea3c3a94891dd3ede827345b4196b3cfa5e15c493d8960df7962b3
approval=58b95f72ec45f36fc132c646745a9622b1b4b979554d57b4dde01754c5f7ad54
```

Local certificate bundle SHA256SUMS verification also passed. Evidence class remains local until publication.

## NLinearModel — LOCAL GPU VERIFIED

Actual construct/fit/predict evidence captured during training and prediction:

```text
prediction_shape=[4,1]
finite=true
train_gpu_event_count=2
predict_gpu_event_count=2
pl_module_device=cuda:0
parameter_device=cuda:0
trainer_root_device=cuda:0
GPU PID visible=true
peak CUDA bytes=18108416
NLINEAR_GPU_RUNTIME=VERIFIED
RC=0
```

## DLinearModel — LOCAL GPU VERIFIED

```text
prediction_shape=[4,1]
finite=true
train_gpu_event_count=2
predict_gpu_event_count=2
pl_module_device=cuda:0
parameter_device=cuda:0
trainer_root_device=cuda:0
GPU PID visible=true
peak CUDA bytes=18121216
DLINEAR_GPU_RUNTIME=VERIFIED
RC=0
```

Post-run parameters observed on CPU do not invalidate these results because train/predict-time callback evidence directly observed CUDA.

## Formal smoke integration attempt — NOT IMPLEMENTED

The first proposed patch intended to connect `smoke_models` to actual CPU/GPU fit/predict did not apply:

```text
git apply --check -> error: corrupt patch at line 381
git apply         -> error: corrupt patch at line 381
```

No `runtime_smoke.py` integration was added by that attempt.

A root Ruff invocation then failed because Ruff was not installed in that invocation environment:

```text
Failed to spawn: ruff
```

Existing `test_runtime_preflight.py` remained 12/12 PASS because the proposed patch was absent.

Correct classification:

```text
PATCH_APPLICATION_FAILED
DEV_TOOLING_MISSING
SMOKE_MODELS_EXECUTION_INTEGRATION=EXECUTION_PENDING
```

## Current status table

| Item | State |
|---|---|
| Darts 0.46.1 source/export discovery | VERIFIED |
| 58 public export rows | VERIFIED inventory surface |
| 58 standalone algorithms | NOT CLAIMED |
| provider/evaluation/OOF foundations | IMPLEMENTED |
| current main bootstrap/preflight | IMPLEMENTED |
| corrected Torch 2.9.1+cu130 contract | LOCAL_VERIFIED / PUBLICATION_PENDING |
| local official bootstrap/approval | LOCAL_VERIFIED |
| NLinear real GPU fit/predict | LOCAL_VERIFIED |
| DLinear real GPU fit/predict | LOCAL_VERIFIED |
| formal `smoke_models` execution | EXECUTION_PENDING |
| source-complete Darts inventory | IN PROGRESS #286 |
| Expanded v2 Darts integration | EXECUTION_PENDING |
| all routable-class smokes | EXECUTION_PENDING |
| six-game OOF | EXECUTION_PENDING |
| Holdout | CLOSED |
| Prospective | CLOSED |

## #286 acceptance still open

Do not close #286 until:

- pinned source-complete forecasting implementation manifest exists;
- abstract/test/internal-only entries are excluded;
- `algorithm_id` / `implementation_id` are preserved;
- base/alias/classifier/wrapper/ensemble/conformal/non-standalone classification is explicit;
- probabilistic/covariate/multivariate/GPU/fit/zero-shot/save-reload capability metadata is complete;
- provider/campaign routes exist for supported entries;
- fail-visible `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `NON_STANDALONE_METHOD` states are explicit;
- deterministic count/collision checks pass;
- focused construct/inference smoke exists for all routable implementations;
- Expanded v2 is integrated without changing Broad 174;
- Holdout/Prospective stay CLOSED.

## Next implementation order

1. Publish the verified Torch dependency/profile/lock correction as a focused code PR.
2. Implement a clean tested runtime-smoke module instead of reusing the corrupt patch.
3. Connect `smoke_models` to fail-closed actual fit/predict evidence.
4. Run notorch CPU representative smokes and Torch NLinear representative smoke through formal preflight.
5. Require new Campaign Approval whose preflight hash binds model-smoke evidence.
6. Extend to every routable Darts implementation.
7. Freeze the Darts Expanded v2 implementation count.
8. Only then run development OOF.

Runtime evidence does not authorize Holdout or Prospective.
