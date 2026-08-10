# Loto Forecast Platform

**ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4**を対象に、統計モデル、機械学習、深層学習、AutoML、時系列基盤モデル（TSFM）、確率モデルを、時系列リークを防いだ共通契約の下で比較・検証・運用するための研究プラットフォームです。

このREADMEは「名前が登録されているモデル」ではなく、**どのライブラリのどのモデルを、どの実行経路で、何の目的に使えるか**が分かることを目的にしています。

> **Code audit basis:** `main@2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8` (2026-08-10)  
> このSHAは機能コードを監査した基準点です。README自身の更新後はGitの最新commitが文書版を識別します。  
> 現在のpackage versionはREADMEへ手書きしません。canonical versionは`loto.version.__version__` / installed package metadata / `loto-build-info`を正本とします。

## 1. このリポジトリでできること

主な用途は次のとおりです。

| やりたいこと | 主な入口 | 実際の役割 |
|---|---|---|
| 6ゲームの仕様・合法性を確認 | `uv run loto3 games` | positions、値域、select/digits family、outcome spaceを確認 |
| 理論上のIID-null基準を確認 | `uv run loto3 theory --game <game> --tau 1` | Hit@±1などの理論参照値を算出 |
| 広いモデル在庫を確認 | `uv run loto3 catalog --counts` / `catalog` | 174-entry broad inventoryを確認 |
| 通常のshared実行モデルを確認 | `uv run loto models list` | `catalog.py`のshared `ModelSpec`を確認 |
| 6ゲーム × broad catalogを同一protocolで計画 | `uv run loto3 campaign --output unused --plan-only` | requested model × game matrixをmaterialize |
| 6ゲーム統一development campaignを実行 | `uv run loto3 campaign ...` | fail-visibleな比較、全seed、baselines、prediction sealing |
| 1つのinstrumented research cycle | `uv run loto3 research ...` | theory / leakage sentinel / statistical comparisonを含む研究cycle |
| 旧shared research configを実行 | `uv run loto experiment research --config ...` | `catalog.py` → candidate/position/foundation worker経路 |
| NeuralForecast AutoModelsをHPO実行 | `uv run loto neuralforecast automodel-run ...` | OptunaまたはRay、CPU/GPU、trial並列、モデル保存 |
| 確率モデル群を調査・実行 | `uv run loto3 probabilistic ...` | 72-model probabilistic catalog、backend probe、run/compare/API |
| TSFM revisionを固定・検証 | `uv run loto3 revisions ...` | broad TSFM inventoryへ明示revision manifestを適用 |
| hierarchy/reconciliationを試す | `uv run loto3 hierarchy ...` | select-game hierarchyとreconciliationを検証 |
| データ取得・正規化 | `uv run loto data acquire ...` | single/multi-game canonical data acquisition |
| run/evidenceをregistryで管理 | `loto experiment status`, registry APIs | run、artifact、approval、release evidenceを管理 |
| APIでrunを操作 | `uv run loto3 probabilistic api-* / run-*` | token付きlocal API、run start/current/stop |
| 実験通知 | `loto notify ...` / probabilistic API TTS | report通知、VOICEVOX連携surface |

重要な境界があります。

```text
モデルが登録されている
!= shared CLIから実行できる
!= isolated providerで実行できる
!= runtime certification済み
!= lottery dataでOOF評価済み
!= Holdout/Prospective通過済み
!= promotion可能
```

この区別をREADME、`docs/MODEL_EXECUTION_MATRIX.md`、runtime evidenceの全てで維持します。

---

## 2. 対応ゲームとgeometry

`src/loto/game/geometry.py`が単一の正本です。ゲームごとのpositions、値域、合法性をモデルやdecoder側で重複hard-codeしない設計です。

| game key | 表示名 | family | positions | 値域 | 主要な合法性 |
|---|---|---|---:|---|---|
| `mini` | ミニロト | select | 5 | 1..31 | distinct / strictly ascending |
| `loto6` | ロト6 | select | 6 | 1..43 | distinct / strictly ascending |
| `loto7` | ロト7 | select | 7 | 1..37 | distinct / strictly ascending |
| `bingo5` | ビンゴ5 | select | 8 | 1..40 | distinct / strictly ascending |
| `numbers3` | ナンバーズ3 | digits | 3 | 0..9 | **位置順序を保持、重複digit可** |
| `numbers4` | ナンバーズ4 | digits | 4 | 0..9 | **位置順序を保持、重複digit可** |

確認:

```bash
uv run loto3 games
uv run loto3 theory --game numbers3 --tau 1
uv run loto3 theory --game loto7 --tau 1
```

select familyとdigits familyは同じ評価式へ無理に押し込めません。例えば`mean_hits`は、selectではset overlap、digitsでは**同一positionの一致数**として計算し、Numbers3/4の順序と重複を失いません。

---

## 3. セットアップ

Python契約は`pyproject.toml`と`uv.lock`が正本です。

```bash
git clone https://github.com/arumajirou/loto_forecast_platform.git
cd loto_forecast_platform
uv sync --locked --extra dev
uv run loto-build-info
uv run loto system doctor
```

Python対応範囲は現在 `>=3.11,<3.14` です。

### 依存lane

| lane | 用途 |
|---|---|
| core (`uv sync`) | NumPy / pandas / Pydantic / scikit-learn / NeuralForecast 3.2.0 / Torch 2.9.1 / Transformers 4.57.6 / HF Hub等 |
| `--extra dev` | pytest / Ruff / mypy / Hypothesis / Optuna / OpenTelemetry |
| `--extra auto-campaign` | Optuna / StatsForecast / psutil |
| `--extra full` | LightGBM / XGBoost / CatBoost / StatsForecast / MLForecast / HierarchicalForecast / Ray / MLflow / telemetry等 |
| `--extra frameworks` | Darts / GluonTS / Lightning / sktime / skforecast / ReservoirPy |
| `--extra tsfm` | Transformers / Accelerate / Chronos forecasting |
| `--extra api` | FastAPI / Uvicorn / HTTP client |
| `--extra postgres` | psycopg / SQLAlchemy |
| `--extra mlflow` | MLflow tracking |
| `environments/**` | AutoGluonやmodel/provider固有のversion-isolated runtime |

Rootへpackageをinstallできることは、そのproviderがcertifiedであることを意味しません。model固有のPython/Torch/CUDA制約がある場合は`environments/**`のisolated lockを優先します。

---

## 4. 3つのモデルsurfaceを区別する

### 4.1 Broad inventory — `catalog_full.py`

```bash
uv run loto3 catalog --counts
uv run loto3 catalog
uv run loto3 catalog --library neuralforecast
uv run loto3 catalog --unpinned
uv run loto3 catalog --csv /tmp/model_catalog.csv
```

現在のbroad inventoryは**174 entries**です。

| library | broad entries | 内容 |
|---|---:|---|
| builtin | 4 | 理論/頻度control |
| sklearn | 7 | 線形・tree ML |
| lightgbm | 2 | boosting |
| xgboost | 1 | boosting |
| catboost | 1 | boosting |
| StatsForecast | 41 | 統計時系列モデル |
| NeuralForecast | 37 | fixed deep models |
| NeuralForecast Auto | 36 | official AutoModels |
| MLForecast Auto | 8 | AutoMLForecast inventory |
| HierarchicalForecast | 10 | reconciliation methods |
| TSFM | 21 | foundation-model inventory |
| AutoGluon | 1 | TimeSeries provider entry |
| Darts | 1 | framework entry |
| GluonTS | 1 | framework entry |
| sktime | 1 | framework entry |
| skforecast | 1 | framework entry |
| ReservoirPy | 1 | ESN entry |
| **total** | **174** | broad planning inventory |

この174は**実行成功数ではありません**。統一campaignは、この在庫を「計画対象」として使い、非対応も結果行として残します。

### 4.2 Shared execution catalog — `catalog.py`

```bash
uv run loto models list --format table
uv run loto models list --available-only --format json
uv run loto models show nf-nhits
uv run loto models export-catalog --output /tmp/shared-models.json
```

`loto experiment research`や`PositionSeriesWorker`が通常参照する実行surfaceです。broad inventoryより意図的に狭いです。

### 4.3 Isolated provider/campaign

一部のlibraryはshared workerに直接入れず、別環境・別contractで安全に実行します。

```text
environments/**
src/loto/*_campaign/**
src/loto/adapters/**
scripts/run_*_provider.py
```

BasicTS、Time-Series-Library、Merlion、sktime、AutoGluonなどは、このsurfaceの存在を必ず確認してから「利用可能」と判断します。

---

## 5. scikit-learn / LightGBM / XGBoost / CatBoost

### Shared candidate models

`src/loto/models/factory.py`から直接fitできる代表ID:

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

位置series側には次もあります。

```text
ridge-position
elasticnet-position
lightgbm-position
```

candidate modelはdraw identity/target列をfeatureから除外してfitし、`predict_proba`、`decision_function`、または`predict`を共通candidate score/probability contractへ変換します。

確率を持つcandidate estimatorを`loto3 campaign`で使う場合、slot-conditioned candidate probabilityをfamily別Hit@±1 decoderへ渡せます。分布identityは`row-normalized-slot-binary-probability-v1`として証拠へ残し、native categorical PMFとは呼びません。

---

## 6. StatsForecast

Broad inventoryは**41モデル**です。例:

```text
AutoARIMA, AutoETS, AutoCES, AutoTheta, AutoMFLES, AutoTBATS,
ARIMA, AutoRegressive, Holt, HoltWinters, HistoricAverage, Naive,
SeasonalNaive, RandomWalkWithDrift, ADIDA, CrostonClassic,
CrostonOptimized, CrostonSBA, IMAPA, TSB, MSTL, TBATS,
Theta family, GARCH, ARCH, UCM, ...
```

ただしshared execution catalogで直接配線済みなのは現在:

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

通常のposition seriesは`StatsForecast.fit()/predict(h=1)`を使用し、Croston/TSBはcandidate-series用の別routeです。

**41 registered != 41 shared-selectable**です。41全件を評価対象として計画したい場合は`loto3 campaign`でcoverageをmaterializeし、routeできない組み合わせも隠さず記録します。

---

## 7. MLForecast / AutoMLForecast

Broad inventoryには8 AutoMLForecast estimatorがあります。

```text
AutoLightGBM
AutoXGBoost
AutoCatboost
AutoLinearRegression
AutoRidge
AutoLasso
AutoElasticNet
AutoRandomForest
```

shared workerで現在直接使うIDは:

```text
mlforecast-ridge
mlforecast-lightgbm
```

`PositionSeriesWorker`がlag featureを構築し、RidgeまたはLightGBMでhorizon=1を予測します。

AutoMLForecast broad inventoryとshared MLForecast 2 routeを同一視しないでください。

---

## 8. NeuralForecast — fixed models

Root coreは`neuralforecast==3.2.0`を固定しています。

Broad inventoryは公式fixed class **37件**:

```text
RNN, GRU, LSTM, TCN, DeepAR, DilatedRNN, MLP,
NHITS, NBEATS, NBEATSx, DLinear, NLinear, TFT,
VanillaTransformer, Informer, Autoformer, PatchTST, FEDformer,
StemGNN, HINT, TimesNet, TimeLLM, TSMixer, TSMixerx,
MLPMultivariate, iTransformer, BiTCN, TiDE, DeepNPTS,
SOFTS, SOFTSSharp, TimeMixer, KAN, RMoK, TimeXer, xLSTM, XLinear
```

shared researchへ直接配線されているfixed modelは現在:

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

workerは`neuralforecast.models`からclassを動的に解決し、horizon、input size、validation window、seed、precision、deviceを設定してfit/predictします。

注意:

- broad 37 classすべてのshared wrapper成功を保証するものではありません。
- `TimesNet`はshared pathでreduced precision要求時にfull precisionへ安全側補正する実装があります。
- multiseries modelは`n_series`契約を満たす必要があります。

---

## 9. NeuralForecast AutoModels — Optuna / Ray

Broad inventoryは公式AutoModel **36件**を持ちます。

```text
AutoRNN, AutoLSTM, AutoGRU, AutoTCN, AutoDeepAR, AutoDilatedRNN,
AutoBiTCN, AutoxLSTM, AutoMLP, AutoNBEATS, AutoNBEATSx, AutoNHITS,
AutoDLinear, AutoNLinear, AutoTiDE, AutoDeepNPTS, AutoKAN, AutoTFT,
AutoVanillaTransformer, AutoInformer, AutoAutoformer, AutoFEDformer,
AutoPatchTST, AutoiTransformer, AutoTimeXer, AutoTimesNet, AutoStemGNN,
AutoHINT, AutoTSMixer, AutoTSMixerx, AutoMLPMultivariate, AutoSOFTS,
AutoSOFTSSharp, AutoTimeMixer, AutoRMoK, AutoXLinear
```

shared AutoModel pathは次をruntimeで解決します。

```text
backend = optuna | ray
num_samples
search_strategy = auto | random | tpe | cmaes
cpus / gpus
parallel_trials
workers / max_gpu_jobs
precision
seed
refit_with_val
model-specific config
```

DB-backed AutoModel run例:

```bash
uv run loto neuralforecast automodel-list --format table

uv run loto neuralforecast automodel-run \
  --db-url sqlite:///data/platform.sqlite3 \
  --table normalized_draws \
  --game numbers4 \
  --models nf-auto-dlinear,nf-auto-nhits \
  --backend optuna \
  --num-samples 10 \
  --cpus 8 \
  --gpus 1 \
  --parallel-trials 2 \
  --seed 1 \
  --output artifacts/nf-auto-example
```

Rayを使う場合は`--backend ray`とし、resource上限を明示します。

`AutoHINT`は特殊routeで、hierarchy、base model、distribution loss、reconciliation/coherenceを個別に組み立てます。

### Repository-local NeuralForecast extensions

公式36 AutoModelとは別に:

| extension | 状態 |
|---|---|
| AutoTimeLLM | `src/loto/neuralforecast/auto_timellm/**` — fail-closed local extension |
| AutoSCINet | `src/loto/neuralforecast/auto_scinet/**` — local extension |
| AutoSegRNN | module上でInactive |
| AutoFreTS | module上でInactive |

「class/fileが存在する」「shared catalogへ配線された」「formal OOF済み」はそれぞれ別状態です。

---

## 10. AutoGluon TimeSeries

AutoGluonはrootへ無理に同居させず、isolated runtimeを使います。

```text
environments/autogluon-timeseries/
scripts/run_autogluon_timeseries_provider.py
```

shared workerから概ね次の形で呼ばれます。

```bash
uv run --project environments/autogluon-timeseries --locked \
  python scripts/run_autogluon_timeseries_provider.py ...
```

protocol v2が現在の標準で、v1は明示compatibility pathです。

既存runtime evidenceではAutoGluon TimeSeries 1.5.0のCPU/fallback certificationと、real Naive fit/predict/save + persisted load/predict smokeが記録されています。**その証拠をGPU certificationへ読み替えません。**

またAutoGluon promotion eligibilityにはhistorical v1とtheory-aware v2があります。v2でもautomatic promotion / automatic retraining / registry writeは明示的に禁止されています。

---

## 11. Darts / GluonTS / ReservoirPy

### Darts

shared `darts-ensemble`はpositionごとに:

```text
NaiveDrift
ExponentialSmoothing
  -> RegressionEnsembleModel
```

をfitして1-step forecastを生成します。

### GluonTS

shared `gluonts-deepar`はTorch `DeepAREstimator` + Student-T outputを利用します。

現在のshared workerはtrainerを`accelerator=cpu`, `devices=1`へ明示固定しています。したがって**GluonTS routeは存在しますが、このpathがCUDA要求を満たすとは記載しません。** GPUを主張する場合は別途actual device evidenceが必要です。

### ReservoirPy

shared `reservoir-esn`はpositionごとに`Reservoir >> Ridge`を構築し、deterministic seed offsetで1-step予測します。

---

## 12. HierarchicalForecast / reconciliation

HierarchicalForecastは独立forecasterではなく、base forecastをcoherentにする**reconciliation layer**です。

core NumPy implementation:

```text
bottom_up
top_down
ols
wls_struct
mint_shrink
```

upstream HierarchicalForecast inventory:

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

試行例:

```bash
uv run loto3 hierarchy --game loto7 --method wls_struct --seed 42
```

一部upstream methodはstrict treeを要求するため、grouped hierarchyでは`UNSUPPORTED_HIERARCHY`になり得ます。10登録 = 10手法が全gameでstandalone実行できる、ではありません。

---

## 13. BasicTS / Time-Series-Library / sktime / skforecast / Merlion

これらはshared catalogだけを見て判断しないlibrary群です。

### BasicTS

```text
src/loto/basicts_campaign/**
scripts/run_basicts_provider.py
```

isolated provider contractでidentity、config validation、dataset compilation、construct/forward/save/load smoke等を扱います。既存contractはBasicTS 1.1.0と明示upstream revisionを使い、CPU-only laneを持ちます。

### Time-Series-Library

```text
src/loto/time_series_library_campaign/**
```

provider/campaignが明示実装する主要model:

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

fit-save / load-predict / upstream discovery / bundle materialization / prediction verification / round-trip verificationを持ちます。

### sktime

```text
src/loto/sktime_campaign/**
```

rolling-origin、validation benchmark、Holdout/Prospective contractを持つ別campaignです。通常の`PositionSeriesWorker` branchとは別です。

### skforecast

`frameworks` extraとbroad catalogにはありますが、現在のshared `PositionSeriesWorker`に直接dispatch branchはありません。したがってshared auto-run可能とは扱いません。

### Merlion

```text
src/loto/merlion_campaign/**
```

version-isolated runtime/provenance/certification surfaceです。174-entry broad countにも通常shared workerにも含めません。

---

## 14. Time-Series Foundation Models (TSFM)

Broad inventoryは21 TSFM entryを持ちます。

```text
Chronos 2 / Chronos Bolt / Chronos T5
TimesFM 2.5
IBM Granite TTM / FlowState / PatchTST / PatchTSMixer
Moirai 2.0 / 1.0
TiRex 2
Toto Open Base / Toto 2.0 4M
MOMENT 1 small / large
Lag-Llama
Kronos
Sundial
TabPFN-TS
T0 alpha
```

shared provider registryは少なくとも次を実装しています。

| shared ID | provider |
|---|---|
| `chronos-bolt-tiny`, `chronos-t5-small`, `chronos-2`, `chronos-2-small` | `ChronosProvider` |
| `timesfm-2.5` | `TimesFMProvider` |
| `granite-ttm` | `GraniteTTMProvider` |
| `tirex` | `TiRexProvider` |
| `moirai` | `MoiraiProvider` |
| `sundial` | `SundialProvider` |
| `tabpfn-ts` | `TabPFNTSProvider` |

unknown providerはsilent fallbackせず`PROVIDER_NOT_IMPLEMENTED`でfail closedします。

### Revision pinning

Broad inventoryのTSFM `revision=None`は「適当なSHAを埋めない」ための設計です。formal executionでは別manifestでimmutable revisionを結びます。

```bash
uv run loto3 revisions template --output /tmp/tsfm-pins.json
uv run loto3 revisions validate --manifest configs/tsfm/verified-revisions.json --require-complete
uv run loto3 revisions report --manifest configs/tsfm/verified-revisions.json --require-complete
```

### Runtime audit evidence

`audit/tsfm-runtime/runtime-status.json`は現在、point-in-time aggregateとして:

```text
total_models=21
runtime_certified_models=19
```

を記録しています。これは**exact runtime identityに対するload/inference evidence**であり、19モデルが全6ゲームでOOF superiorityを持つという意味ではありません。blocked/gated/licensing状態も個別recordで確認してください。

---

## 15. 確率モデル / Probabilistic Programming

`loto3 probabilistic`は通常の174 broad forecast inventoryとは別に、**72-model probabilistic catalog**を持ちます。

```bash
uv run loto3 probabilistic catalog-list
uv run loto3 probabilistic native-coverage
uv run loto3 probabilistic backends
uv run loto3 probabilistic compatibility \
  --model-id pp-conditional-bernoulli-fixed-k \
  --game loto7 \
  --backend builtin
```

familyには次のようなものがあります。

```text
conjugate / dynamic_conjugate / empirical_bayes
bayesian_regression / hierarchical / state_space
changepoint / regime_switching / mixture / nonparametric
copula / gaussian_process / tree_bayesian
fixed_subset / calibration / decision / ensemble
count / ordinal / semi_parametric / deep_probabilistic
```

optional backend surface:

```text
builtin
PyMC / ArviZ / PyMC-BART
NumPyro + JAX
Pyro + Torch
CmdStanPy
BlackJAX + JAX
TensorFlow Probability
```

代表的なnative implementationにはfixed-k Conditional Bernoulli、multinomial DGLM、Gaussian copula categorical、BOCPD Dirichlet-categoricalなどがあります。

実行はconfig-drivenです。

```bash
uv run loto3 probabilistic validate-config --config <config.yaml>
uv run loto3 probabilistic plan --config <config.yaml>
uv run loto3 probabilistic smoke --config <config.yaml>
uv run loto3 probabilistic run --config <config.yaml>
uv run loto3 probabilistic status --run-dir <run-dir>
uv run loto3 probabilistic diagnose --run-dir <run-dir>
uv run loto3 probabilistic compare --run-dir <run-dir>
```

---

## 16. 6ゲーム統一 all-model × all-game development campaign

全ゲーム横断で比較する場合の正規入口は**`loto3 campaign`**です。

### まずplanだけ確認

```bash
uv run loto3 campaign --output unused --plan-only
```

特定library/modelだけに絞る場合:

```bash
uv run loto3 campaign \
  --output unused \
  --games numbers3,numbers4,loto7 \
  --models logistic,nf-nhits,chronos-2 \
  --plan-only
```

### 実データdevelopment run

入力directoryには対象gameの`<game>.csv`を置きます。

```bash
RUN_ID="campaign-$(date +%Y%m%d-%H%M%S)"

uv run loto3 campaign \
  --input-dir /absolute/path/to/canonical-csvs \
  --output "artifacts/unified-campaign/${RUN_ID}" \
  --seeds 42,1729,20260730 \
  --folds 5 \
  --test-size 20 \
  --min-train-size 100 \
  --holdout-size 50 \
  --device auto \
  --precision 32 \
  --max-trials 10 \
  --parallel-trials 1
```

### 小さいsynthetic smoke

```bash
uv run loto3 campaign \
  --synthetic --synthetic-rows 40 \
  --games numbers3,loto7 \
  --models logistic \
  --seeds 1 \
  --folds 1 --test-size 2 --min-train-size 12 --holdout-size 4 \
  --device cpu \
  --output /tmp/loto-unified-smoke
```

### Campaignの重要な性質

- requested **model × game pairをexactly one row**として残す。
- `SUCCEEDED`だけでなく、`PARTIAL_SEEDS`, `FAILED`, `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `NON_STANDALONE_METHOD`を保持する。
- `matrix_complete=true`は「全組合せに結果行がある」という意味で、全組合せ成功ではない。
- full broad runを計画できることと、174 × 6のreal-data成功が完了済みであることは別。

---

## 17. 評価指標、baselines、seed

Primary metricは**Hit@±1**です。

必須metrics:

```text
hit_at_1 / within_tau_rate
position_hit_at_1
all_positions_hit_at_1 / all_positions_within_tau_rate
MAE
MSE
RMSE
```

geometry-general metric layerではselect/digitsの意味を分離しています。

Mandatory baselines:

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

Default campaign seeds:

```text
42
1729
20260730
```

各metricは全seedを保持し、meanだけでなくpopulation variance、standard deviation、min/max、worst value、worst seedを残します。**best seedだけを選んでchampionにする設計ではありません。**

---

## 18. Hit@±1-optimal decoder

Probability-bearing candidate routeは、単純MAPだけでなく「±1以内に入る期待効用」を最大化する`WITHIN_TAU` objectiveを使えます。

```text
candidate probabilities
  -> row-normalized-slot-binary-probability-v1
  -> family dispatch
       digits: positionごとのwindow-mass最大化
       select: ascending/distinct legalityを守るconstrained DP
  -> legal point prediction
```

select gameではstrictly increasing tupleを壊さず、digits gameではposition order/repetitionを維持します。

point-only modelへ架空の確率分布を作ることはしません。decoder objective、distribution identity、post-processing identityはevidenceへ残します。

---

## 19. Prediction sealing / leakage防止

各formal evaluationで重要なのは「実測を見てから予測を書かない」ことです。

Unified campaignでは各`game × candidate × seed`について:

```text
Train-only fit / eligible history
-> predict
-> prediction evidenceを書込 (actuals_known=false)
-> fsync
-> SHA-256を固定
-> その後にtarget actualをscoring stageで読む
-> metrics
```

既存output directoryは再利用せず、Run IDを分離します。

Formal scientific ordering:

```text
Train
-> Validation / OOF development
-> authorized Holdout
-> sealed Prospective prediction
-> later actual scoring
-> promotion eligibility
```

HoldoutやProspectiveをdevelopment runが勝手に開くことはありません。

---

## 20. Theory-aware Hit@±1 threshold

`src/loto/evaluation/theory_guard.py`は、目標値を単なる固定%として扱わず、game geometryのIID-null理論値と結びます。

2つのsemantics:

```text
absolute
excess_vs_iid_null
```

例として`excess_vs_iid_null`のtarget=0.0は「IID-null exact referenceと同じabsolute target」を意味します。

absolute targetがIID-null ceilingを超える場合、単に「高い目標だからよい」と受理せず、明示的なalternative hypothesisなしではfail closedします。

IID-null ceilingは**指定IID-null分布下のexact optimum**であり、あらゆるbiased processに対する普遍的上限とは主張しません。

---

## 21. Promotion eligibility — manual only

AutoGluon campaignにはhistorical v1とtheory-aware v2 policyがあります。

v2は:

- `game`を必須化
- scoring evidenceのsealed `game_id`とpolicy gameの一致を必須化
- `tau=1`に固定
- theory-aware semanticsから実際に比較するabsolute Hit@±1 targetを導出
- aggregate/worst prospective windowを同じtargetで評価
- Holdout→Prospective degradationを評価
- mandatory baselines全件を比較

します。

しかし、全ruleがpassしてもdecisionは:

```text
ELIGIBLE_FOR_HUMAN_APPROVAL
```

までです。コード上で常に:

```text
human_approval_required = true
automatic_promotion = false
automatic_retraining = false
registry_write_allowed = false
promotion_status = NOT_PROMOTED
```

を維持します。

したがって、**promotion eligibility == production promotionではありません。**

---

## 22. 事前MDE / power planning

`src/loto/evaluation/power_analysis.py`は「改善が見えなかった」のか「そもそもsample sizeでその差を検出できない」のかを事前に区別するためのplanning utilityです。

method:

```text
paired-score-normal-approximation-v1
```

提供API:

```python
from loto.evaluation.power_analysis import (
    PowerPlan,
    minimum_detectable_effect,
    power_curve,
    required_paired_draws,
)
```

`PowerPlan`は:

- alpha
- target power
- multiplicity
- one-sided positive paired alternative

を固定し、multiplicityにはBonferroni planning alphaを使います。

```python
plan = PowerPlan(alpha=0.05, target_power=0.80, multiplicity=10)

required = required_paired_draws(
    effect=0.02,
    score_sd=0.20,
    plan=plan,
)

mde = minimum_detectable_effect(
    n_draws=500,
    score_sd=0.20,
    plan=plan,
)

curve = power_curve((100, 250, 500, 1000), 0.20, plan=plan)
```

`score_sd`はtarget windowを見る前にdevelopment/pilot evidenceまたは宣言済みsimulationから固定する必要があります。これは**planning evidenceであり、p-value、Holdout result、promotion decisionではありません。**

---

## 23. Artifacts / registry / approval / integrity

Platformには予測だけでなく、run/evidence control-planeがあります。

主なCLI:

```bash
uv run loto experiment status
uv run loto artifact put --file <path> --store <artifact-store>
uv run loto artifact verify-bundle --bundle <bundle>
uv run loto approval request ...
uv run loto approval decide ...
uv run loto3 integrity generate --root .
uv run loto3 integrity check --root .
```

PostgreSQL lane、MLflow lane、OpenTelemetry、Prometheus-compatible metrics、structured event/evidence layerを組み合わせられます。具体的なrunがどのstoreを使ったかは、そのrunのconfig/artifact manifestを権威としてください。

---

## 24. Local API / run control / VOICEVOX

Probabilistic execution surfaceにはauthenticated local APIがあります。

```bash
uv run loto3 probabilistic api-token-create --root .
uv run loto3 probabilistic api-serve --root .
uv run loto3 probabilistic api-health --root .
uv run loto3 probabilistic api-profiles --root .

uv run loto3 probabilistic run-start --root . --profile fast_cpu
uv run loto3 probabilistic run-current --root .
uv run loto3 probabilistic run-stop --root .
```

VOICEVOX endpointを利用するTTS surface:

```bash
uv run loto3 probabilistic tts-status --root .
uv run loto3 probabilistic tts-play --root . --text "実験が完了しました"
uv run loto3 probabilistic tts-synthesize \
  --root . \
  --text "検証結果を保存しました" \
  --output /tmp/result.wav
```

API/TTS availabilityはlocal service/backendの実状態に依存します。

---

## 25. 目的別の推奨運用

### A. 「まず何が登録されているか見たい」

```bash
uv run loto3 catalog --counts
uv run loto3 catalog --library neuralforecast
uv run loto models list --format table
```

### B. 「特定modelをshared pathで試したい」

1. `loto models show <id>`で`ModelSpec`確認。
2. 必要extra/providerをinstall。
3. small synthetic/focused run。
4. load/inference/device evidence確認。
5. OOFへ進む場合はprotocol/data snapshotを固定。

### C. 「全library/modelを6ゲームで同条件比較したい」

1. `loto3 campaign --plan-only`でmatrix確認。
2. 6ゲームのimmutable canonical CSV snapshotを準備。
3. resource budgetとseedを固定。
4. development campaignを新Run IDで実行。
5. `model_game_results.csv`の成功だけでなくfailure statusも解析。
6. mandatory baselines / seed variance / leakage / prediction sealを検証。
7. OOF evidenceが十分になるまでHoldoutを開かない。

### D. 「AutoModelをOptuna/Rayで探索したい」

`loto neuralforecast automodel-run`を使い、trial数、parallel trials、CPU/GPU、seed、precisionを明示します。modelごとの失敗を別Run ID/evidenceで残し、best trialだけで全model評価を置換しません。

### E. 「Foundation modelを使いたい」

1. broad catalogのrepo IDを見る。
2. verified revision manifestを確認。
3. shared providerまたはisolated providerの有無を確認。
4. exact model/revision/runtimeのcertification evidenceを確認。
5. OOFはruntime certificationと別runとして実施。

### F. 「promotion判定まで進めたい」

```text
runtime certification
-> leakage-safe OOF
-> authorized Holdout
-> multiple sealed Prospective windows
-> theory-aware target + baseline/degradation rules
-> ELIGIBLE_FOR_HUMAN_APPROVAL
-> human approval
```

自動promotionや自動registry writeへ短絡しません。

---

## 26. Capability stateの読み方

文書では次の段階を使います。

```text
REGISTERED
-> DEPENDENCY_DECLARED
-> IMPLEMENTED
-> SHARED_ROUTABLE or PROVIDER_ROUTABLE
-> RUNTIME_CERTIFIED
-> LOTTERY_COMPATIBLE
-> OOF_EVALUATED
-> HOLDOUT_EVALUATED
-> PROSPECTIVE_EVALUATED
-> PROMOTION_ELIGIBLE
-> HUMAN_APPROVED / PROMOTED (別の明示操作)
```

後段を前段から推測しません。

---

## 27. 現在の科学的境界 / 非主張

このREADMEが説明するのは**機能・実行契約・既存runtime evidence**です。現時点で次を自動的には主張しません。

- 174 broad entriesすべてがshared-routableである。
- 174 entriesすべてが6ゲームすべてでruntime成功した。
- 実データの完全な174 × 6 campaignが完了済みである。
- 19 runtime-certified TSFMが全6ゲームでOOF superiorityを示した。
- WITHIN_TAU decoderが全modelのreal OOFを改善する。
- lottery drawが非IIDである。
- Holdoutが開放済みである。
- Prospective evidenceが完成している。
- championが存在する。
- production promotionが承認済みである。

Open scientific/runtime workのcurrent snapshotは`docs/STATUS.md`を参照してください。

---

## 28. Documentation map

最初に読む順:

1. [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md) — library/model/CLI/providerを目的別に引ける詳細運用表
2. [`docs/STATUS.md`](docs/STATUS.md) — 現在の監査snapshotと科学的境界
3. [`docs/MODEL_EXECUTION_MATRIX.md`](docs/MODEL_EXECUTION_MATRIX.md) — registered/shared/provider/runtime evidenceの詳細
4. [`docs/UNIFIED_EVALUATION_CAMPAIGN.md`](docs/UNIFIED_EVALUATION_CAMPAIGN.md) — all-model × all-game development campaign
5. [`docs/evaluation_protocol/PROTOCOL_V2.md`](docs/evaluation_protocol/PROTOCOL_V2.md) — formal evaluation protocol
6. [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) — 要件
7. [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md) — 外部仕様
8. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture
9. [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md) — data/leakage contract
10. [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) — verification gates
11. [`docs/CURRENT_RUNBOOK.md`](docs/CURRENT_RUNBOOK.md) — 現在の実行手順
12. [`docs/CURRENT_HANDOFF.md`](docs/CURRENT_HANDOFF.md) — 次作業への引継ぎ
13. [`docs/DOCUMENTATION_POLICY.md`](docs/DOCUMENTATION_POLICY.md) — current/historical/generated evidenceの読み方

`docs/MODEL_INVENTORY.md`はgenerated broad inventoryです。手書きの「実行可能数」として扱わないでください。

---

## 29. Repository validation

開発中はfocused testを優先し、最後にfull gateをまとめます。

```bash
uv sync --locked --extra dev
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run python -m compileall -q src scripts tests
uv run pytest -q
```

Runtime-sensitive providerはこれに加えて、exact model/revision/environmentでload → inference → output checks → device evidence → unload/reloadを検証します。

---

## 30. 重要な原則

このplatformの目的は「モデル名を大量に並べること」ではありません。

**同じゲーム、同じ時点、同じeligible data、同じmetrics/baselines、全seed、予測固定、明示resource budgetの下で比較し、失敗も含めて再現できる証拠を残すこと**が中心です。
