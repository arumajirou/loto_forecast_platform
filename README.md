# Loto Forecast Platform

6ゲーム（ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4）を対象に、統計・機械学習・深層学習・時系列基盤モデルを **同一のleakage-safe評価条件で比較する研究＋運用基盤** です。

現在のpackage versionはREADMEへ手書きしません。canonical versionは`loto.version.__version__`、installed CLI、またはpackage metadataから確認してください。

## 最初に読む資料

- [`docs/MODEL_EXECUTION_MATRIX.md`](docs/MODEL_EXECUTION_MATRIX.md) — **コード・worker・provider・runtime evidenceから確認した実際のモデル/ライブラリ実行経路**
- [`docs/STATUS.md`](docs/STATUS.md) — GitHub/Linear/科学進捗を突合した時点付き監査スナップショット
- [`docs/README.md`](docs/README.md) — live code / generated inventory / runtime evidence / historical evidenceの読み分け
- [`docs/DOCUMENTATION_POLICY.md`](docs/DOCUMENTATION_POLICY.md) — stale/current/historical資料の更新規約
- [`docs/MODEL_INVENTORY.md`](docs/MODEL_INVENTORY.md) — 自動生成された**広い在庫**。`loto3 catalog --counts`が対応する
- [`docs/evaluation_protocol/PROTOCOL_V2.md`](docs/evaluation_protocol/PROTOCOL_V2.md) — formal評価protocol

固定されたActions run ID、PR状態、main SHA、PCのOS可否などは時間とともに変わります。READMEではそれらを恒久的な「current値」として扱いません。

## Code-grounded capability audit — 2026-08-10 16:47 JST

この節は`main@0f7585bca90fe9c1578909018a2dc24fcfdc12cb`の実コードとruntime evidenceを基準にしています。

今回確認した主要な事実:

```text
broad_catalog=src/loto/models/catalog_full.py
shared_execution_catalog=src/loto/models/catalog.py
shared_candidate_runtime=src/loto/models/factory.py
shared_series_runtime=src/loto/models/workers.py
shared_foundation_registry=src/loto/models/providers/registry.py
shared_research_orchestrator=src/loto/orchestration/research.py
v3_scientific_orchestrator=src/loto/orchestration/research_v3.py
TSFM_RUNTIME_AUDIT=21 judged / 19 CERTIFIED / 2 BLOCKED
```

重要なのは、**174 registered estimators = 174 shared-runnable models ではない**ことです。同時に、174件に入っていないから実装がないとも限りません。BasicTS、Time-Series-Library、Merlion、sktime campaign、ローカルNeuralForecast拡張などは別のisolated provider/campaignとして存在します。

## 2種類のcatalog

### 1. Broad inventory — `catalog_full.py`

```text
uv run loto3 catalog --counts
uv run loto3 catalog
uv run loto3 catalog --unpinned
```

これは174件の広い在庫、family/capability/repo metadataを確認するためのsurfaceです。

### 2. Shared execution catalog — `catalog.py`

```text
uv run loto models list --format json
uv run loto models show <model_id>
uv run loto models export-catalog --output <path>
```

こちらは`loto experiment research`が`get_model_spec()`で実際に参照する`ModelSpec`群です。

したがって、モデルの実行可否を確認するときは最低でも以下を順に見ます。

```text
catalog_full registration
-> catalog.py shared ModelSpec
-> factory.py/workers.py dispatch
-> providers/** or isolated campaign/provider
-> exact runtime evidence
-> OOF/scientific evidence
```

## 実際のshared research path

`uv run loto experiment research --config ...`は次のコード経路です。

```text
loto.cli
  -> orchestration/research.py
    -> catalog.get_model_spec()
      -> task=candidate
         -> RuntimeModel in factory.py
      -> task=position_series/foundation
         -> PositionSeriesWorker in workers.py
```

`RuntimeModel`はbuiltin/scikit-learn/LightGBM/XGBoost/CatBoost候補モデルを直接fitします。

`PositionSeriesWorker`は現在、実コードとして次をdispatchします。

```text
sklearn/lightgbm position series
StatsForecast
MLForecast
NeuralForecast fixed
NeuralForecast AutoModels
AutoHINT special path
AutoGluon TimeSeries isolated subprocess
Darts
GluonTS
ReservoirPy
shared foundation providers
```

`uv run loto3 research`は別系統です。`research_v3.py`はmandatory predictorを内蔵し、追加モデルはcallerから`predictors`として注入する構造なので、174 catalogを自動的に全実行するコマンドではありません。

## Installation tiers

正確な依存契約は[`pyproject.toml`](pyproject.toml)と各`environments/**`のlockfileです。

| install/lane | 実コード上の主用途 |
|---|---|
| `uv sync` | core, scikit-learn, NeuralForecast 3.2.0, Torch 2.9.1, Transformers 4.57.6, HF Hub等 |
| `uv sync --extra dev` | pytest / Ruff / mypy / Hypothesis / Optuna / telemetry |
| `uv sync --extra auto-campaign` | Optuna / StatsForecast / resource inspection |
| `uv sync --extra api` | FastAPI / Uvicorn API lane |
| `uv sync --extra postgres` | PostgreSQL data source |
| `uv sync --extra mlflow` | MLflow tracking |
| `uv sync --extra frameworks` | Darts / GluonTS / Lightning / sktime / skforecast / ReservoirPy |
| `uv sync --extra tsfm` | Transformers / Accelerate / Chronos forecasting |
| `uv sync --extra full` | LightGBM / XGBoost / CatBoost / StatsForecast / MLForecast / HierarchicalForecast / NeuralForecast / Optuna / Ray等 |
| `environments/**` | AutoGluonやmodel/provider固有のversion-isolated runtime |

Root extraにpackageがあることは、そのproviderのruntime certificationを意味しません。

## Broad inventory — 174 registered entries

`docs/MODEL_INVENTORY.md` / `loto3 catalog --counts`が扱う広い在庫は以下です。

| library | registered count | broad role |
|---|---:|---|
| builtin | 4 | controls |
| sklearn | 7 | ML baseline |
| lightgbm | 2 | boosting |
| xgboost | 1 | boosting |
| catboost | 1 | boosting |
| statsforecast | 41 | statistical forecasting |
| neuralforecast | 37 | fixed neural models |
| neuralforecast_auto | 36 | official AutoModels |
| mlforecast_auto | 8 | AutoMLForecast inventory |
| hierarchicalforecast | 10 | reconciliation methods |
| tsfm | 21 | foundation-model inventory |
| autogluon | 1 | AutoML provider entry |
| darts | 1 | framework entry |
| gluonts | 1 | framework entry |
| sktime | 1 | framework entry |
| skforecast | 1 | framework entry |
| reservoirpy | 1 | ESN entry |
| **total** | **174** | broad generated inventory |

以下では、この件数ではなく**実行経路**を説明します。

## Builtin / sklearn / boosting

`factory.py`に具体的なconstructorがあります。

Shared candidate execution:

```text
uniform
frequency
logistic
random-forest
extra-trees
hist-gradient-boosting
lightgbm-classifier
xgboost-classifier
catboost-classifier
```

`RuntimeModel.fit_candidate()`はtarget/identity列を特徴量から除外し、fit後に`predict_proba` / `decision_function` / `predict`を候補確率へ変換します。

## StatsForecast

Broad inventoryは41件ですが、shared execution catalogで直接選択できるIDは現在少なくとも次です。

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

通常のposition-seriesは`StatsForecast.fit()/predict(h=1)`、Croston/TSBは37候補のbinary candidate seriesへ変換する別経路です。

したがって**41 registered != 41 shared-selectable**です。

## MLForecast

Broad inventoryには8 `mlforecast_auto` entriesがありますが、shared research catalogの実行IDは現在:

```text
mlforecast-ridge
mlforecast-lightgbm
```

です。`PositionSeriesWorker._mlforecast()`がlag付き`MLForecast`を作り、RidgeまたはLightGBMでhorizon 1を予測します。

## NeuralForecast fixed

Broad inventoryは37 fixed modelsです。`catalog.py`でshared researchへ直接配線されているfixed modelは現在:

```text
DLinear
NLinear
NHITS
NBEATS
NBEATSx
TiDE
TCN
GRU
LSTM
DeepAR
TFT
PatchTST
TimesNet
TSMixer
TimeMixer
iTransformer
VanillaTransformer
```

workerはclassを`neuralforecast.models`から動的importし、h=1、input size、validation window、seed、CPU/GPUを設定してfit/predictします。

コード上の注意:

- `TSMixer`, `TimeMixer`, `iTransformer`にはこのshared workerで`n_series=7`を設定します。
- `TimesNet`はreduced precision要求時も`32-true`へ固定する処理があります。
- broad catalogにある37 classすべてについて、このshared wrapperのruntime成功を自動的に意味しません。

## NeuralForecast AutoModels

shared execution catalogにはofficial AutoModel familyが実装され、`_neuralforecast_auto()`が以下をruntimeで解決します。

```text
Optuna / Ray backend
search algorithm
num_samples
cpus / gpus
parallel_trials
refit_with_val
search_strategy
precision
seed
n_series
```

`AutoHINT`は特別経路で、7 position + totalのhierarchy、DLinear base、Normal DistributionLoss、reconciliation、coherence errorを実際に構築します。

### 追加ローカル拡張

official shared AutoModel listとは別に、現在のcodebaseには以下も存在します。

| extension | actual module state |
|---|---|
| AutoTimeLLM | `src/loto/neuralforecast/auto_timellm/**` — fail-closed local extension |
| AutoSCINet | `src/loto/neuralforecast/auto_scinet/**` — local SCINet/AutoSCINet extension |
| AutoSegRNN | `src/loto/neuralforecast/auto_segrnn/**` — module自身が `Inactive` と明記 |
| AutoFreTS | `src/loto/neuralforecast/auto_frets/**` — module自身が `Inactive` と明記 |

「ファイルが存在する」「classをconstructできる」「shared catalogへ登録済み」「formal OOF済み」は別です。

## AutoGluon TimeSeries

AutoGluonはroot環境へ直接importするのではなく、shared workerからisolated runtimeをsubprocess実行します。

```text
environments/autogluon-timeseries/
scripts/run_autogluon_timeseries_provider.py
```

実行形:

```text
uv run --project environments/autogluon-timeseries --locked python scripts/run_autogluon_timeseries_provider.py ...
```

protocol v2がshared defaultで、v1は明示compatibility pathです。

Merged PR #237の実行証拠ではAutoGluon TimeSeries 1.5.0のCPU/fallback runtime certificationと、shared production workerでのreal Naive fit/predict/save + persisted load/predictまでPASSしています。positive GPU inference certificationは同PRでは主張していません。

## Darts / GluonTS / ReservoirPy

### Darts

shared `_darts()`は各positionに:

```text
NaiveDrift
ExponentialSmoothing
-> RegressionEnsembleModel
```

をfitして1-step予測します。

### GluonTS

shared `_gluonts()`はTorch `DeepAREstimator` + `StudentTOutput`を実際にconstruct/train/predictします。

ただし現在のsourceではtrainerが明示的に:

```text
accelerator=cpu
devices=1
```

へhard-codeされています。source内にも`--device cuda/auto`との未整合を示すaudit commentがあります。したがって「GluonTS workerあり」は正しいですが「このshared pathがCUDA要求を満たす」は未確認です。

### ReservoirPy

shared `_reservoir_esn()`は各positionに`Reservoir >> Ridge`を構築し、seedを固定して1-step予測します。

## HierarchicalForecast

HierarchicalForecastは通常の予測workerではなく**reconciliation layer**です。

core NumPy implementation:

```text
bottom_up
top_down
ols
wls_struct
mint_shrink
```

optional upstream `hierarchicalforecast` execution:

```text
BottomUp
BottomUpSparse
TopDown
TopDownSparse
MiddleOut
MiddleOutSparse
MinTrace
MinTraceSparse
OptimalCombination
ERM
```

`reconcile_with_hierarchicalforecast()`は実packageをimportし、constructor、`fit_predict`、shape/finite/coherenceを検証します。

number hierarchyはtotal/parity/decade/numberを含むgrouped hierarchyなので、strict-treeを必要とするupstream methodは`UNSUPPORTED_HIERARCHY`になり得ます。10件登録されていることと、全10手法が全hierarchyで実行可能であることは同義ではありません。

## sktime / skforecast

### sktime

`frameworks` extraとbroad catalogだけでなく、別のisolated provider/campaignがあります。

```text
src/loto/sktime_campaign/**
```

ここにはprovider protocol、rolling-origin、validation benchmark、Holdout scoring、Prospective contractがあります。ただしshared `PositionSeriesWorker`に`sktime` branchはありません。

### skforecast

`frameworks` extraとbroad catalogには存在しますが、監査した`PositionSeriesWorker.forecast()`には直接の`skforecast` dispatch branchがありません。shared `loto experiment research`から自動実行可能とは記載しません。

## BasicTS

BasicTSは174-entry catalogとは別のisolated providerです。

```text
src/loto/basicts_campaign/**
scripts/run_basicts_provider.py
```

現在のstrict contractはBasicTS `1.1.0`、upstream revision `c2bb6e31e591167e84459775a21a62e70a5893ce`を固定し、以下のoperationを持ちます。

```text
identity
validate_config
compile_dataset
construct_forward_save_load_smoke
```

Numbers3 / Numbers4 / MiniLoto / Loto6 / Loto7 dataset payloadを受け、現v1 laneはCPU-only / no-CPU-fallback契約です。

## Time-Series-Library

これも174-entry catalogとは別のprovider/campaignです。

```text
src/loto/time_series_library_campaign/**
```

`execute_request()`に現在明示されているfit-save/load-predict model path:

```text
DLinear
TSMixer
LightTS
SegRNN
FreTS
SCINet
TimeFilter
TiDE
FiLM
```

加えてupstream model discovery、training bundle materialization、data validation、prediction-file verification、round-trip verificationがあります。

## Merlion

Merlionも別系統です。

```text
src/loto/merlion_campaign/**
```

moduleはisolated runtime / provenance / certification contractとして存在します。174-entry broad catalogやshared `PositionSeriesWorker`へ入っているモデルとは別に扱います。

## Foundation models — shared provider registry

`PositionSeriesWorker._foundation()`は実際に:

```text
get_foundation_provider(spec)
-> provider.load()
-> provider.predict(history)
-> provider.inspect_properties()
-> provider.close()
```

を呼びます。

shared registryに現在実装されているprovider:

| ID/family | actual provider |
|---|---|
| Chronos / Chronos Bolt Tiny / Chronos T5 Small / Chronos 2 / Chronos 2 Small | `ChronosProvider` |
| Sundial | `SundialProvider` |
| TimesFM / TimesFM 2.5 | `TimesFMProvider` |
| Granite TTM | `GraniteTTMProvider` |
| TiRex | `TiRexProvider` |
| Moirai | `MoiraiProvider` |
| TabPFN-TS | `TabPFNTSProvider` |

未実装IDは`ProviderNotImplemented`へ落ち、`PROVIDER_NOT_IMPLEMENTED`でfail closedします。

## Foundation models — runtime audit reality

Broad TSFM inventory 21件について、現在の実行証拠は:

```text
audit/tsfm-runtime/runtime-status.json
configs/tsfm/verified-revisions.json
```

です。

aggregate counters:

```text
total_models=21
certified_models=19
blocked_models=2
pending_models=0
judged_models=21
judged_progress_percent=100.0
```

Blocked:

| model | reason |
|---|---|
| `moirai-1.0-base` | pinned snapshotにrequired config/model weightsがない。licenseはpersonal non-commercial scope |
| `t0-alpha` | gated access required |

残る19件はaggregate runtime auditで`CERTIFIED`です。ただし**certification scopeはモデルごとに異なります**。

例:

- Chronos-2: CUDA runtime、7 series output、no CPU fallback、quantile/mean shapes、VRAM/PID evidenceを保持。
- Kronos: real CUDA inferenceはCERTIFIEDだがnative financial OHLCV contractで、`lottery_domain_compatibility_certified=false`。
- Moirai 2.0 Small: full inferenceはCERTIFIEDだが`lottery_domain_compatibility_certified=false`、personal/non-commercial license scope。
- MOMENT: runtime execution evidenceがあってもpretrained forecast headの有無/finetuning requirementを別に扱う。

したがって`CERTIFIED`を「宝くじOOFへそのまま投入済み」と読み替えてはいけません。

### runtime-status内の不整合

同じ`runtime-status.json`は:

```text
certified_models=19
total_models=21
formal_certification_rate_percent=42.9
```

も保持しています。19/21は約90.5%なので、この`42.9` fieldは古い定義/古い集計値と整合しません。audit artifact自体は履歴証拠として改竄せず、現在値として率を説明する場合は**19/21 countersを優先し、不整合を明記**します。

## TSFM revision pinの読み方

`configs/tsfm/verified-revisions.json`には21件すべてのverified revisionがあります。

一方、`loto3 catalog --unpinned`はbroad catalogのbase declarationだけを見るため`UNPINNED`を返し得ます。

つまり:

```text
catalog field UNPINNED
!= repository内にverified revisionが存在しない

verified revision exists
!= runtime inference certified
```

formal runではverified revision + artifact hash + runtime evidenceを同じexecution identityへ固定します。

## Capability levels

モデル/ライブラリの状態は以下で記述します。

```text
REGISTERED
DEPENDENCY_DECLARED
IMPLEMENTED
SHARED_ROUTABLE
PROVIDER_ROUTABLE
RUNTIME_CERTIFIED
LOTTERY_COMPATIBLE
OOF_EVALUATED
HOLDOUT_EVALUATED
PROSPECTIVE_EVALUATED
PROMOTION_ELIGIBLE
```

**単一の`available=true`へ潰しません。**

## Scientific acceptance policy

Primary KPIは`Hit@±1`です。formal比較では併せて:

```text
hit_at_1
position_hit_at_1
all_positions_hit_at_1
mae
mse
rmse
```

を保存します。

最低限のbaseline:

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

評価規則:

- Train / Validation / Holdout / Prospectiveを時間順で分離する。
- Scaler、Encoder、特徴量選択、HPO/チューニングはTrain内だけでfitする。
- OOFは複数seedを全て保持し、mean / population variance / worst value / worst seedを保存する。
- best-seed-only採用は禁止する。
- 予測値はtarget actual参照前にimmutable write + SHA-256 + timestampで固定する。
- 異なる`protocol_hash`を同じleaderboardへ混ぜない。
- valid outcomeとして`NO_MODEL_BEATS_BASELINE` / `champion=null`を認める。

## Current Timer Base 84M scientific boundary

PR #240でengineering foundationはmerge済みですが、GitHub Issue #239 / Linear TAJ-12のformal科学工程は別です。

```text
formal_timer_oof_run=false
holdout_opened=false
prospective_opened=false
accuracy_claim=false
champion_claim=false
promotion=false
```

今回のcode capability auditは既存実装/実行証拠を読み直したもので、新しいモデル推論やOOFを実行したものではありません。

## Data / evidence / tracking

Raw dataは不変の正本として扱い、formal campaignではsource/data/split/feature/code/model/runtime/protocol identityとSHA-256を固定します。

Formal Run IDには設定、data hash、code hash、Git commit、model/revision、seed、予測、実測、評価値、stdout/stderr、resource/GPU情報を結びます。既存のMLflow/PostgreSQL/DuckDB/Parquet等の契約を優先します。

## Repository design sources

- [`specs/001-full-coverage/spec.md`](specs/001-full-coverage/spec.md)
- [`specs/001-full-coverage/plan.md`](specs/001-full-coverage/plan.md)
- [`specs/001-full-coverage/research.md`](specs/001-full-coverage/research.md)
- [`specs/001-full-coverage/tasks.md`](specs/001-full-coverage/tasks.md)
- [`.specify/memory/constitution.md`](.specify/memory/constitution.md)

## Historical reports are not deleted

古い`VERIFICATION_REPORT`、`HANDOFF`、CI run ID、SHA256SUMSは、その時点のevidenceです。現在値と違うからという理由で過去の観測結果を改竄しません。現在の読み方は[`docs/DOCUMENTATION_POLICY.md`](docs/DOCUMENTATION_POLICY.md)に従います。

## Theoretical bounds

[`docs/THEORETICAL_BOUNDS.md`](docs/THEORETICAL_BOUNDS.md)を参照してください。MAE下限とHit@±1上限は別目的であり、formal selection priorityはHit@±1を先に固定します。

## License / research disclaimer

本ソフトウェアは時系列予測手法の研究を目的とします。宝くじの当選を予測する能力は主張しません。正式な性能主張は、固定済みprotocol、リーク検査、baseline比較、multi-seed集約、prediction sealing、必要なruntime evidenceを通過した実測結果だけを根拠にします。
