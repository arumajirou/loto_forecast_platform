# Darts Current State

```text
status: PARTIALLY_VERIFIED / EXPANDED_V2_PHASE2A_IMPLEMENTED / PHASE2B_RUNTIME_OPEN
integration_base: 179bcbc9a51a60f0badfe7faa25f3818ab686229
main_target: darts==0.46.1
tracking: GitHub #286 / Linear TAJ-27
Broad_v1: 1 umbrella
public_exports: 58
Expanded_v2_source_identities: 55
base_Expanded_v2: 244
Darts_aware_Expanded_v2: 298
Holdout: CLOSED
Prospective: CLOSED
```

この文書はDartsの `Broad v1 = 1` と実装候補数を混同しないためのcurrent-state資料です。**Broad 1は互換umbrellaであり、Dartsに1モデルしかないという意味ではありません。**

## Expanded v2 Phase 2a — source identity integration

Darts 0.46.1のpublic forecasting export fixtureは **58 names** です。Phase 2aでは次の3件をstandalone implementation denominatorから明示的に除外します。

| public export | classification | canonical/reason |
|---|---|---|
| `EnsembleModel` | `ABSTRACT_BASE` | concrete ensemble implementationsを別identityとして扱う |
| `RandomForest` | `DEPRECATED_ALIAS` | `RandomForestModel`へ正規化 |
| `RegressionModel` | `DEPRECATED_ALIAS` | `SKLearnModel`へ正規化 |

```text
58 public exports
- 1 abstract base
- 2 deprecated aliases
= 55 source implementation identities
```

Source authority:

- `src/loto/models/darts_source_inventory.py` — pinned Darts 0.46.1 fixture、explicit exclusions、family、manifest SHA-256;
- `src/loto/models/expanded_inventory_v2.py` — current main Expanded inventoryへDartsだけをoverlayするcomposition;
- `scripts/report_expanded_model_inventory_v2.py` — Darts-aware JSON report。

55件はすべてfail-closedで開始します。

```text
source_declared=true
source_version=0.46.1
evidence_class=SOURCE_DECLARED
routability=UNKNOWN
runtime_status=NOT_RUN
runtime_certified=false
execution_surface=darts_provider_pending
capabilities=source_declared only
```

source exportやinventory登録をruntime成功へ読み替えません。

## Current combined Expanded-v2 count

current main `implementation_catalog.py` はAutoGluon 37、GluonTS 9、skforecast 27を含み **244** を導出します。Darts-aware compositionは、そのcurrent baseからDarts Broad copy 1だけを55 source identitiesへ置換します。

```text
244 - Darts Broad copy 1 + Darts source identities 55 = 298
```

Broad v1は引き続き **174**、Broad campaign plannerは **174 × 6 = 1,044** のままです。298はruntime-certified count、OOF count、Holdout count、Prospective countではありません。

## Existing execution foundation

Repositoryには次が実装されています。

- strict request/response contracts;
- `discover` / `fit_predict` provider modes;
- local/statistical、regression/boosting、Torch、foundation、ensemble/conformal matrices;
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

これらのexplicit matricesは55 identityすべてのruntime certificationを意味しません。

## Runtime bootstrap boundary

```bash
uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_notorch.yaml \
  --repository-root .

uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_torch.yaml \
  --repository-root .
```

Current `run_runtime_preflight()`はPython/lock/package/import/export/CUDA/nvidia-smi等を検証します。`RuntimeProfile.smoke_models`からactual construct/fit/predictを実行する正式統合はまだ未完です。

## 2026-08-13 local Torch evidence

Local exact-worktreeでは次を確認しています。

```text
darts=0.46.1
torch=2.9.1+cu130
torch CUDA=13.0
pytorch-lightning=2.6.5
Python=3.13
GPU=NVIDIA GeForce RTX 5070 Ti
```

Local official bootstrap evidence:

```text
DARTS_TORCH_ENV=VERIFIED
focused test_runtime_preflight=12/12 PASS
overall_status=PASS
preflight_status=PASS
approval_created=true
campaign_execution_allowed=true
BOOTSTRAP_RC=0
```

このruntime evidenceはsource inventory 55件全体へ横展開しません。

### NLinearModel — LOCAL GPU VERIFIED

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

### DLinearModel — LOCAL GPU VERIFIED

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

Post-run parametersがCPUへ戻っていても、train/predict-time callbackでCUDA device、GPU PID、VRAMを直接観測しているためCPU fallbackとは判定しません。

## Formal smoke integration — still open

最初の`smoke_models` actual fit/predict統合patchは適用されませんでした。

```text
git apply --check -> error: corrupt patch at line 381
git apply         -> error: corrupt patch at line 381
SMOKE_MODELS_EXECUTION_INTEGRATION=EXECUTION_PENDING
```

既存preflight PASSを55件のconstruct/fit/predict PASSへ読み替えません。

## Current status table

| Item | State |
|---|---|
| Darts 0.46.1 public export denominator 58 | VERIFIED SOURCE BOUNDARY |
| explicit exclusions 3 | IMPLEMENTED |
| source-backed Expanded identities 55 | IMPLEMENTED / FAIL-CLOSED |
| Broad Darts umbrella 1 | FROZEN / COMPATIBILITY |
| current base Expanded v2 = 244 | MERGED MAIN BASE |
| Darts-aware source-backed Expanded v2 = 298 | IMPLEMENTED CONTRACT |
| 55 runtime-certified implementations | NOT CLAIMED |
| provider/evaluation/OOF foundations | IMPLEMENTED |
| bootstrap/preflight foundation | IMPLEMENTED |
| local corrected Torch 2.9.1+cu130 evidence | LOCAL_VERIFIED |
| NLinear real GPU fit/predict | LOCAL_VERIFIED |
| DLinear real GPU fit/predict | LOCAL_VERIFIED |
| formal `smoke_models` execution | EXECUTION_PENDING |
| per-identity capability/routing classification | PHASE 2B OPEN |
| all routable-class smokes | EXECUTION_PENDING |
| six-game OOF | EXECUTION_PENDING |
| Holdout | CLOSED |
| Prospective | CLOSED |

## #286 acceptance remaining after Phase 2a

Phase 2a resolves the deterministic 58→55 source denominator. #286 remains open until Phase 2b completes:

- per-identity probabilistic/covariate/multivariate/GPU/fit/zero-shot/save-reload capability metadata;
- game compatibility and provider/campaign routes;
- explicit `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `NON_STANDALONE_METHOD` states;
- focused construct/fit/predict smoke for every routable implementation;
- output shape/finite checks;
- expected vs observed CPU/GPU device;
- GPU PID/VRAM and CPU fallback detection where applicable;
- save/reload/predict evidence where supported;
- complete six-game development OOF only after runtime stabilization.

## Next implementation order

1. Keep the 55-identity source manifest/hash deterministic for Darts 0.46.1.
2. Classify all 55 identities by capability, dependency, game compatibility and routing.
3. Implement a clean tested runtime-smoke module and connect `smoke_models` to actual fit/predict.
4. Reuse the verified NLinear/DLinear callback evidence criteria in the formal harness.
5. Extend CPU/GPU/runtime certification to every routable Darts implementation.
6. Preserve explicit failure states for non-routable/unsupported identities; no silent skips.
7. Only after runtime stabilization, run identical-condition chronological development OOF.

Runtime evidence does not authorize Holdout or Prospective.
