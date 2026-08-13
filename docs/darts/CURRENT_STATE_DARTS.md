# Darts Current State

```text
status: PARTIALLY_VERIFIED / EXPANDED_V2_PHASE2A_IMPLEMENTED / PHASE2B_RUNTIME_OPEN
integration_base: 45bcf60fa04fc3736e3a73760039254573abf4c8
main_target: darts==0.46.1
tracking: GitHub #286 / Linear TAJ-27
Broad_v1: 1 umbrella
public_exports: 58
Expanded_v2_source_identities: 55
combined_Expanded_v2: 272
Holdout: CLOSED
Prospective: CLOSED
```

この文書は、Dartsの `Broad v1 = 1` と実装候補数を混同しないためのcurrent-state資料です。**Broad 1は互換umbrellaであり、Dartsに1モデルしかないという意味ではありません。**

## Expanded v2 Phase 2a — source identity integration

Darts 0.46.1のversioned public forecasting export fixtureは **58 names** です。Phase 2aでは次の3件をstandalone implementation denominatorから明示的に除外します。

| public export | classification | canonical/reason |
|---|---|---|
| `EnsembleModel` | `ABSTRACT_BASE` | concrete ensemble implementationsを別identityとして扱う |
| `RandomForest` | `DEPRECATED_ALIAS` | `RandomForestModel`へ正規化 |
| `RegressionModel` | `DEPRECATED_ALIAS` | `SKLearnModel`へ正規化 |

したがってsource-backed Darts Expanded identityは次のとおりです。

```text
58 public exports
- 1 abstract base
- 2 deprecated aliases
= 55 source implementation identities
```

単一正本:

- `src/loto/models/darts_source_inventory.py`
- discoveryは同fixtureを参照し、58-name listを重複保持しない
- authoritative compositionは`src/loto/models/expanded_inventory_v2.py`
- `scripts/report_expanded_model_inventory.py`はauthoritative compositionを出力する

55件はすべて初期状態をfail-closedにします。

```text
runtime_status=NOT_RUN
runtime_certified=false
execution_surface=darts_provider_pending
capabilities=source_declared only
```

登録やsource exportの存在をruntime成功へ読み替えません。

## Combined Expanded-v2 count

current source-backed compositionはAutoGluon Phase 1、GluonTS Phase 3、Darts Phase 2aを同時に保持します。

```text
174 Broad v1
- AutoGluon umbrella 1
- GluonTS umbrella 1
- Darts umbrella 1
+ AutoGluon implementations 37
+ GluonTS implementations 9
+ Darts source implementations 55
= 272 Expanded-v2 identities
```

Broad v1は引き続き **174**、Broad campaign plannerは **174 × 6 = 1,044** のままです。272はruntime-certified count、OOF count、Holdout count、Prospective countではありません。

## Source discovery foundation

- Darts target: `0.46.1`;
- versioned public forecasting export fixture: **58 names**;
- deterministic discovery;
- abstract/import/non-class/alias/signature/capability metadata;
- optional dependency failures remain visible.

Explicit represented execution groups include:

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

## Runtime foundation

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

Bootstrap:

```bash
uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_notorch.yaml \
  --repository-root .

uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_torch.yaml \
  --repository-root .
```

Current `run_runtime_preflight()`はPython/lock/package/import/export/CUDA/nvidia-smi等を検証しますが、`RuntimeProfile.smoke_models`からactual construct/fit/predictを実行する正式統合はまだ未完です。

## 2026-08-13 local Torch correction — publication boundary

Local exact-worktreeでは次のcorrective runtimeを確認しています。

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

このdependency/profile/lock evidenceは、対応するcode/profile/lockがmainへ反映された範囲だけcurrent-main certificationへ昇格できます。

## NLinearModel — LOCAL GPU VERIFIED

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

Post-run parametersがCPUへ戻っていても、train/predict-time callbackでCUDA device、GPU PID、VRAMを直接観測しているためCPU fallbackとは判定しません。

## Formal smoke integration — still open

最初の`smoke_models` actual fit/predict統合patchは適用されませんでした。

```text
git apply --check -> error: corrupt patch at line 381
git apply         -> error: corrupt patch at line 381
```

したがって正しい分類は次です。

```text
SMOKE_MODELS_EXECUTION_INTEGRATION=EXECUTION_PENDING
```

既存preflight PASSを55件のconstruct/fit/predict PASSへ読み替えません。

## Current status table

| Item | State |
|---|---|
| Darts 0.46.1 public source fixture 58 | VERIFIED |
| explicit exclusions 3 | VERIFIED |
| source-backed Expanded identities 55 | IMPLEMENTED / FAIL-CLOSED |
| Broad Darts umbrella 1 | FROZEN / COMPATIBILITY |
| combined source-backed Expanded v2 = 272 | IMPLEMENTED CONTRACT |
| 55 runtime-certified implementations | NOT CLAIMED |
| provider/evaluation/OOF foundations | IMPLEMENTED |
| current bootstrap/preflight foundation | IMPLEMENTED |
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

Phase 2a resolves the deterministic source manifest/count/collision boundary. #286 remains open until Phase 2b completes:

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

1. Keep the 55-identity source manifest/hash deterministic and immutable for Darts 0.46.1.
2. Classify all 55 identities by capability, dependency, game compatibility and routing.
3. Implement a clean tested runtime-smoke module and connect `smoke_models` to actual fit/predict.
4. Reuse the already verified NLinear/DLinear callback evidence criteria in the formal harness.
5. Extend CPU/GPU/runtime certification to every routable Darts implementation.
6. Preserve explicit failure states for non-routable/unsupported identities; no silent skips.
7. Only after runtime certification, run identical-condition chronological development OOF.

Runtime evidence does not authorize Holdout or Prospective.
