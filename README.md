# Loto Forecast Platform

現在のpackage versionはREADMEへ手書きしません。canonical versionは`loto.version.__version__`、installed CLI、またはpackage metadataから確認してください。

6ゲーム（ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4）を対象に、統計・機械学習・深層学習・時系列基盤モデルを **同一のleakage-safe評価条件で比較する研究＋運用基盤** です。

このREADMEでは「どのライブラリ・モデルが登録されているか」「どの追加依存が必要か」「どの用途で使うか」「登録済みとruntime成功をどう区別するか」を具体的に示します。

## Current execution status — 2026-08-10

```text
CURRENT_OPERATOR_EXECUTION_ENVIRONMENT=native Windows only
LINUX_EXECUTION_CURRENTLY_AVAILABLE=false
WSL_EXECUTION_CURRENTLY_AVAILABLE=false
PR_240_STATE=merged
PR_240_MERGE_SHA=0bb4680b2d26cfd32788381f580d86a4acd0fb6d
SCIENTIFIC_PROGRESS=18%
FORMAL_OOF_RUN=false
TIMER_INFERENCE_RUN=false
HOLDOUT_OPENED=false
PROSPECTIVE_OPENED=false
ACCURACY_CLAIM=false
CHAMPION_CLAIM=false
PROMOTION=false
```

PR #240でTimer Base 84M leakage-safe OOFの実装基盤、Windows portability、テスト、関連資料は`main`へ統合済みです。ただし、**科学検証完了を意味しません**。現在PCでは正式なdevelopment-only data sourceのセットアップと最終`EvaluationProtocolV2`固定が先です。

現在のnative Windows self-hosted GitHub Actions runnerは、runner identity、checkout、exact uv、managed Python、universal lock、Windows dependency resolution、wheel build、wheel install/import、tracked-files-cleanまで成功済みです。

詳細:

- [`docs/WINDOWS_INSTALL.md`](docs/WINDOWS_INSTALL.md)
- [`docs/windows_only_execution/README.md`](docs/windows_only_execution/README.md)
- [`docs/windows_only_execution/RUNBOOK.md`](docs/windows_only_execution/RUNBOOK.md)
- [`docs/windows_only_execution/HANDOFF.md`](docs/windows_only_execution/HANDOFF.md)
- [`docs/MODEL_INVENTORY.md`](docs/MODEL_INVENTORY.md)
- [`src/loto/models/catalog_full.py`](src/loto/models/catalog_full.py)

## まず確認するコマンド

モデル件数やrevision状態はREADMEの手書き値ではなく、実行時catalogを正とします。

```powershell
uv --version
uv run loto3 games
uv run loto3 catalog --counts
uv run loto3 catalog --unpinned
uv run loto3 integrity check
```

TSFM revision manifestは次で生成・検証します。

```powershell
uv run loto3 revisions template
uv run loto3 revisions validate
```

> `catalog`への登録は、package import成功、model load成功、GPU推論成功、正式なOOF認証を意味しません。runtime certificationは別工程です。

## インストール層

`pyproject.toml`では機能をoptional extraへ分離しています。新PCでは必要な層だけを追加し、いきなり`full`へ依存しない運用を推奨します。

| install | 主な内容 | 主用途 | Windows上の扱い |
|---|---|---|---|
| `uv sync` | NumPy / pandas / scikit-learn / SciPy / Pydantic / NeuralForecast / Torch / Transformers等 | core研究・NeuralForecast | 基本層 |
| `uv sync --extra dev` | pytest / Ruff / mypy / Hypothesis / Optuna / telemetry SDK | 開発・検証 | 推奨 |
| `uv sync --extra auto-campaign` | Optuna / StatsForecast / psutil | 自動探索campaign | 選択導入 |
| `uv sync --extra postgres` | psycopg / SQLAlchemy | PostgreSQL data source | DB構築後に使用 |
| `uv sync --extra mlflow` | MLflow | run / artifact tracking | 任意 |
| `uv sync --extra frameworks` | Darts / GluonTS / Lightning / sktime / skforecast / ReservoirPy | framework比較 | 選択導入 |
| `uv sync --extra tsfm` | Transformers / Accelerate / Chronos forecasting | TS foundation model基盤 | モデルごとの追加packageに注意 |
| `uv sync --extra full` | LightGBM / XGBoost / CatBoost / StatsForecast / MLForecast / HierarchicalForecast / NeuralForecast / Optuna / Ray / telemetry / Plotly等 | 全機能開発 | native Windowsではtargeted extra優先。formal実行前に依存解決を再認証する |

## ライブラリ・モデル利用一覧

`docs/MODEL_INVENTORY.md`の自動生成inventoryでは、現在 **174 registered estimators** を管理します。以下は「何に使うか」を含めた運用表です。

| library | catalog件数 | 代表モデル / 内容 | 主なtask | 使い方 | 依存・注意 |
|---|---:|---|---|---|---|
| `builtin` | 4 | `uniform`, `frequency`, `position-median`, `position-modal` | candidate / position | 必須control・理論基準 | coreで常時利用可能 |
| `sklearn` | 7 | Logistic, Ridge, ElasticNet, RF, ExtraTrees, HistGB, calibrated logistic | candidate / position | 外生特徴量付きML baseline | core依存 |
| `lightgbm` | 2 | classifier / position regressor | candidate / position | tree boosting + exogenous | `full` |
| `xgboost` | 1 | XGBClassifier | candidate | probability + exogenous | `full` |
| `catboost` | 1 | CatBoostClassifier | candidate | probability + exogenous | `full` |
| `statsforecast` | 41 | AutoARIMA, AutoETS, SeasonalNaive, Croston系, Theta系, TBATS等 | position_series | 統計baseline / intermittent / conformal | `auto-campaign`または`full` |
| `neuralforecast` | 37 | NHITS, NBEATSx, TFT, PatchTST, iTransformer, xLSTM等 | position_series | 固定architecture深層予測 | coreに`neuralforecast==3.2.0` |
| `neuralforecast_auto` | 36 | AutoNHITS, AutoTFT, AutoPatchTST, AutoXLinear等 | position_series | official AutoModel + HPO | search backendはruntime解決。Optuna/Ray利用時は環境認証必須 |
| `mlforecast_auto` | 8 | AutoLightGBM / XGBoost / CatBoost / linear / Ridge / Lasso / ElasticNet / RF | position_series | lag特徴量 + exogenous + HPO | `full` |
| `hierarchicalforecast` | 10 | BottomUp, TopDown, MinTrace, ERM等 | reconciliation | number / decade / parity / totalのcoherence | `full` |
| `tsfm` | 21 | Chronos-2, TimesFM 2.5, Moirai, TiRex-2, Toto, TTM, Lag-Llama等 | foundation | zero-shot / pretrained foundation model | 全21件はcatalog登録。model package・revision・licenseを個別確認 |
| `autogluon` | 1 top-level provider | AutoGluon TimeSeries | position_series | AutoML provider | catalog登録とruntime discovery/certificationを分離 |
| `darts` | 1 | RegressionEnsembleModel | position_series | ensemble framework | `frameworks` |
| `gluonts` | 1 | DeepAREstimator | position_series | probabilistic deep forecasting | `frameworks` |
| `sktime` | 1 | EnsembleForecaster | position_series | framework ensemble | `frameworks` |
| `skforecast` | 1 | ForecasterRecursive | position_series | lag ML + exogenous | `frameworks` |
| `reservoirpy` | 1 | ESN | position | reservoir computing | `frameworks` |

### taskの意味

| task | 入出力の考え方 | 代表用途 |
|---|---|---|
| `candidate` | 各候補番号の確率・ranking | uniform / frequency / tree classifier / TabPFN-TS |
| `position` | 各抽選位置を直接回帰 | median/modal / Ridge / LightGBM regressor / ESN |
| `position_series` | 各位置を時系列としてforecast | StatsForecast / NeuralForecast / MLForecast / Darts等 |
| `foundation` | pretrained TSFMへcontextを渡してzero-shot等でforecast | Chronos / TimesFM / Moirai / TiRex / Toto等 |
| `reconciliation` | 既存forecastを階層制約へ整合 | HierarchicalForecast |

## NeuralForecast — fixed models 37

固定architectureを公平に比較する層です。モデルfamily、exogenous、probabilistic、multivariate能力はcatalogで明示します。

<details>
<summary>登録済み37モデル</summary>

`RNN`, `GRU`, `LSTM`, `TCN`, `DeepAR`, `DilatedRNN`, `MLP`, `NHITS`, `NBEATS`, `NBEATSx`, `DLinear`, `NLinear`, `TFT`, `VanillaTransformer`, `Informer`, `Autoformer`, `PatchTST`, `FEDformer`, `StemGNN`, `HINT`, `TimesNet`, `TimeLLM`, `TSMixer`, `TSMixerx`, `MLPMultivariate`, `iTransformer`, `BiTCN`, `TiDE`, `DeepNPTS`, `SOFTS`, `SOFTSSharp`, `TimeMixer`, `KAN`, `RMoK`, `TimeXer`, `xLSTM`, `XLinear`.

</details>

能力上の重要な区分:

- **exogenous対応**: `NBEATSx`, `TFT`, `TSMixerx`, `TimeXer`, `BiTCN`, `TiDE`
- **probabilistic扱い**: `DeepAR`, `DeepNPTS`, `TFT`, `HINT`
- **multivariate扱い**: `StemGNN`, `MLPMultivariate`, `TSMixer`, `TSMixerx`, `SOFTS`, `SOFTSSharp`, `TimeMixer`, `RMoK`, `iTransformer`
- **FFT系でprecision注意**: `TimesNet`, `FEDformer`, `Autoformer`, `TimeMixer`はreduced precisionを前提にせず32-trueを要求する設計

使い分けの例:

| 目的 | 優先候補 |
|---|---|
| 強い単変量deep baseline | NHITS / NBEATS / PatchTST |
| 外生変数あり | NBEATSx / TFT / TiDE / BiTCN / TimeXer / TSMixerx |
| 確率予測 | DeepAR / DeepNPTS / TFT / HINT |
| 複数位置共有表現 | iTransformer / TSMixer / MLPMultivariate等 |
| 新しいarchitecture比較 | xLSTM / XLinear / SOFTSSharp |

## NeuralForecast AutoModels — 36

固定モデルと同じfamilyをAutoModelとして探索します。**AutoModelの最良trialだけを採用して科学結果にしない**ことが重要です。formal評価では複数seed、OOF、mean / variance / worstを保存します。

<details>
<summary>登録済み36 AutoModels</summary>

`AutoRNN`, `AutoLSTM`, `AutoGRU`, `AutoTCN`, `AutoDeepAR`, `AutoDilatedRNN`, `AutoBiTCN`, `AutoxLSTM`, `AutoMLP`, `AutoNBEATS`, `AutoNBEATSx`, `AutoNHITS`, `AutoDLinear`, `AutoNLinear`, `AutoTiDE`, `AutoDeepNPTS`, `AutoKAN`, `AutoTFT`, `AutoVanillaTransformer`, `AutoInformer`, `AutoAutoformer`, `AutoFEDformer`, `AutoPatchTST`, `AutoiTransformer`, `AutoTimeXer`, `AutoTimesNet`, `AutoStemGNN`, `AutoHINT`, `AutoTSMixer`, `AutoTSMixerx`, `AutoMLPMultivariate`, `AutoSOFTS`, `AutoSOFTSSharp`, `AutoTimeMixer`, `AutoRMoK`, `AutoXLinear`.

</details>

Catalog上の能力は`position + hpo`で、multivariate baseはAuto側にも引き継がれます。search backend / search algorithmはruntimeで解決するため、**Optuna / Rayがimportできるだけで正式成功とはしません**。

## StatsForecast — 41

統計モデルは深層モデルの前に必ず比較すべき基準です。特に`SeasonalNaive`, `Naive`, `HistoricAverage`はmandatory controlsです。

<details>
<summary>登録済み41モデル</summary>

`AutoARIMA`, `AutoETS`, `AutoCES`, `AutoTheta`, `AutoMFLES`, `AutoTBATS`, `ARIMA`, `AutoRegressive`, `SimpleExponentialSmoothing`, `SimpleExponentialSmoothingOptimized`, `SeasonalExponentialSmoothing`, `SeasonalExponentialSmoothingOptimized`, `Holt`, `HoltWinters`, `HistoricAverage`, `Naive`, `RandomWalkWithDrift`, `SeasonalNaive`, `ConformalSeasonalPool`, `WindowAverage`, `SeasonalWindowAverage`, `ADIDA`, `CrostonClassic`, `CrostonOptimized`, `CrostonSBA`, `IMAPA`, `TSB`, `MSTL`, `MFLES`, `TBATS`, `Theta`, `OptimizedTheta`, `DynamicTheta`, `DynamicOptimizedTheta`, `GARCH`, `ARCH`, `SklearnModel`, `ConstantModel`, `ZeroModel`, `NaNModel`, `UCM`.

</details>

用途:

- ARIMA系: `AutoARIMA`, `ARIMA`, `AutoRegressive`
- ETS / smoothing系: `AutoETS`, SES, Holt, HoltWinters
- 季節baseline: `SeasonalNaive`
- intermittent series: `ADIDA`, Croston family, `IMAPA`, `TSB`
- decomposition: `MSTL`, `MFLES`, `TBATS`, `UCM`
- conformal: `ConformalSeasonalPool`
- volatility: `GARCH`, `ARCH`

番号の出現有無を系列化した場合はintermittent-demand系が自然な比較対象になるため、Croston familyをcatalogに含めています。

## MLForecast Auto — 8

lag / rolling / calendar等の特徴量をML estimatorへ渡してAutoMLForecastで探索する層です。

`AutoLightGBM`, `AutoXGBoost`, `AutoCatboost`, `AutoLinearRegression`, `AutoRidge`, `AutoLasso`, `AutoElasticNet`, `AutoRandomForest`.

主な用途:

- lag特徴量 + tree boosting
- calendar / draw index等のexogenous比較
- linear / regularized linearを含む軽量baseline
- NeuralForecast Autoとの同一OOF条件比較

## HierarchicalForecast — 10 reconciliation methods

`BottomUp`, `BottomUpSparse`, `TopDown`, `TopDownSparse`, `MiddleOut`, `MiddleOutSparse`, `MinTrace`, `MinTraceSparse`, `OptimalCombination`, `ERM`.

これらは予測モデルそのものではなく、**予測後のcoherenceを担保するreconciliation層**です。number → decade → parity → total等の階層を同時に扱う場合に使用します。reconciliationあり/なしは同一評価protocolで比較し、後処理だけで有利な条件を作らないようにします。

## Time-Series Foundation Models — 21

TSFMはpretrained checkpointを用いる`foundation` taskです。catalogへの登録と、formal reproducibilityのためのrevision fixationは別です。

| model_id | upstream repo | package / interface | 想定用途・注意 |
|---|---|---|---|
| `chronos-2` | `amazon/chronos-2` | `chronos` / `Chronos2Pipeline` | zero-shot, probabilistic, covariate-capable |
| `chronos-bolt-tiny` | `amazon/chronos-bolt-tiny` | `chronos` | 軽量・CPU候補 |
| `chronos-t5-small` | `amazon/chronos-t5-small` | `chronos` | tokenized Chronos |
| `chronos-t5-base` | `amazon/chronos-t5-base` | `chronos` | tokenized Chronos |
| `timesfm-2.5-transformers` | `google/timesfm-2.5-200m-transformers` | `transformers` | Transformers-native、`trust_remote_code`不要の方を優先 |
| `granite-ttm-r2` | `ibm-granite/granite-timeseries-ttm-r2` | `transformers` | Apache-2.0 TTM |
| `granite-flowstate-r1` | `ibm-granite/granite-timeseries-flowstate-r1` | `transformers` | 小型zero-shot候補 |
| `granite-patchtst` | `ibm-granite/granite-timeseries-patchtst` | `transformers` | PatchTST系 |
| `granite-patchtsmixer` | `ibm-granite/granite-timeseries-patchtsmixer` | `transformers` | PatchTSMixer系 |
| `moirai-2.0-small` | `Salesforce/moirai-2.0-R-small` | `uni2ts` | probabilistic foundation model |
| `moirai-1.0-base` | `Salesforce/moirai-1.0-R-base` | `uni2ts` | probabilistic foundation model |
| `tirex-2` | `NX-AI/TiRex-2` | `tirex` | xLSTM-based TSFM |
| `toto-open-base` | `Datadog/Toto-Open-Base-1.0` | `toto` | probabilistic |
| `toto-2.0-4m` | `Datadog/Toto-2.0-4m` | `toto` | probabilistic |
| `moment-1-small` | `AutonLab/MOMENT-1-small` | `momentfm` | representation model、forecasting head要確認 |
| `moment-1-large` | `AutonLab/MOMENT-1-large` | `momentfm` | representation model |
| `lag-llama` | `time-series-foundation-models/Lag-Llama` | `lag_llama` | probabilistic |
| `kronos-base` | `NeoQuasar/Kronos-base` | `kronos` | discrete-token financial series model |
| `sundial-base` | `thuml/sundial-base-128m` | `transformers` | probabilistic |
| `tabpfn-ts` | `Prior-Labs/TabPFN-v2-clf` | `tabpfn_time_series` | candidate matrixへtabular foundation modelを適用 |
| `t0-alpha` | `theforecastingcompany/t0-alpha` | `tfc` | gated。terms未承認ではknown-blockedとして扱う |

### TSFMで必ず確認するもの

1. `repo_id`
2. exact `revision`
3. model / config / tokenizer等のartifact SHA-256
4. license / gated access
5. package version
6. context length / horizon / target dimension
7. load → input → inference → output shape → finite values
8. actual device / GPU PID / VRAM / CPU fallback
9. prediction sealがactual参照前に固定されたこと

`docs/MODEL_INVENTORY.md`では現在のTSFM 21件を`UNPINNED`として扱っています。**revision未固定のままformal protocolへ昇格させません**。

## Framework tier

| provider | catalog entry | 使い方 | runtime上の注意 |
|---|---|---|---|
| AutoGluon | `autogluon-timeseries` | `TimeSeriesPredictor`によるAutoML | source-declared / runtime-discovered / runtime-importable / runtime-certifiedを分ける |
| Darts | `darts-ensemble` | `RegressionEnsembleModel` | ensemble比較 |
| GluonTS | `gluonts-deepar` | `DeepAREstimator` | probabilistic position series |
| ReservoirPy | `reservoir-esn` | ESN | position regression |
| sktime | `sktime-ensemble` | EnsembleForecaster | framework ensemble |
| skforecast | `skforecast-recursive` | ForecasterRecursive | lag ML + exogenous |

これらは`frameworks` extraで導入できるものと、別途provider packageを要求するものがあります。**catalog entryが存在するだけでruntime certifiedとは表示しません**。

## Builtin / sklearn / boosting tier

### 常時利用するcontrol

- `uniform`: exact theoretical uniform。candidate probability/rankingのmandatory control
- `frequency`: 過去頻度ベース
- `position-median`: 理論MAE-floor predictor
- `position-modal`: 理論Hit@±tau ceiling predictor

### sklearn

- `logistic`: candidate probability + exogenous
- `ridge`: position regression + exogenous
- `elastic-net`: position regression + exogenous
- `random-forest`: candidate probability + exogenous
- `extra-trees`: candidate probability + exogenous
- `hist-gradient-boosting`: candidate probability + exogenous
- `isotonic-calibrated-logistic`: probability calibration比較

### optional boosting

- `lightgbm-classifier`
- `lightgbm-position`
- `xgboost-classifier`
- `catboost-classifier`

## 何をどう比較するか

モデルを「使える」と判定するレベルを分離します。

| Level | 意味 | 例 |
|---|---|---|
| 1. Registered | catalogにmodel_idがある | 174件inventory |
| 2. Dependency available | packageが解決・import可能 | `uv sync` / extra |
| 3. Runtime loadable | model/checkpointを実際にloadできる | provider smoke |
| 4. Inference verified | shape / finite / device / GPU PID / VRAM確認 | runtime certification |
| 5. OOF evaluated | leakage-safe OOFでbaselineと同条件比較 | formal scientific gate |
| 6. Holdout eligible | OOF evidenceとprotocol固定後のみ | Holdout開封前gate |
| 7. Promotion eligible | Holdout/Prospective、license、runtime evidence等を通過 | champion / promotion |

**Level 1だけを見て「利用可能」「成功」とは記載しません。**

## 推奨する比較順序

1. builtin controls
2. StatsForecastのmandatory controls
3. sklearn / boosting
4. StatsForecast全統計モデル
5. NeuralForecast fixed
6. NeuralForecast Auto
7. MLForecast Auto
8. TSFM zero-shot / pretrained
9. framework tier
10. ensemble / reconciliation

すべて同じeligible folds、同じdata boundary、同じPrimary KPIで比較します。

## Scientific acceptance policy

最優先指標は`Hit@±1`です。併記する指標は`MAE`、`MSE`、`RMSE`、位置別`Hit@±1`、全位置`Hit@±1`です。formal比較では最低限、Random、固定値、平均、中央値、直近値、頻度、統計モデルを同一protocolで比較します。

Train / Validation / Holdout / Prospectiveは時間順で分離し、Scaler、Encoder、特徴量選択、HPOはTrain内だけで行います。OOFは複数seedの平均・分散・最悪値を保存し、最良seedだけでは採用しません。予測値は実測参照前にSHA-256と時刻で固定します。

### formal runで禁止すること

- HoldoutをHPOへ使う
- Prospective actualを予測固定前に読む
- seedのbestだけを採用する
- TSFM revision未固定のまま再現可能と主張する
- CPU fallbackしたrunをGPU成功として扱う
- catalog登録だけでruntime successと扱う
- 異なるprotocol hashの結果を同じleaderboardへ混ぜる

## DBからモデルを使う場合

SQLite / PostgreSQLはraw sourceの一形態です。DB接続が成功しただけではformal dataset確定にはなりません。

formal OOF前には最低限、次を固定します。

1. source identity
2. raw query
3. chronological cutoff
4. duplicate / missing / ordering / future leakage checks
5. immutable snapshot
6. snapshot SHA-256
7. Holdout / Prospective rowsがdevelopment snapshotへ混入していないこと

現在の新PCではhistorical `loto` DBが未セットアップであり、既存Windows PostgreSQL 18はhistorical `loto` clusterではないことを確認済みです。したがって、DBを無理に既存clusterへ合わせず、正式なdata source setupを先に行います。

## Repository design sources

- 仕様: [`specs/001-full-coverage/spec.md`](specs/001-full-coverage/spec.md)
- 計画・設計判断: [`specs/001-full-coverage/plan.md`](specs/001-full-coverage/plan.md)
- 一次情報調査ログ: [`specs/001-full-coverage/research.md`](specs/001-full-coverage/research.md)
- タスク: [`specs/001-full-coverage/tasks.md`](specs/001-full-coverage/tasks.md)
- 憲章: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)

## 設計上の核心

### 1. ゲーム幾何の単一情報源

`loto.game.GameGeometry` が universe / slot / family を一元管理します。`select`族（重複なし・昇順）と`digits`族（重複可・先頭0有意）を別物として扱います。

### 2. protocol_hash

評価条件をSHA-256で固定し、異なるhash同士の比較を拒否します。最終コードidentity・frozen development snapshot・resource/package identityを固定した`EvaluationProtocolV2` hashが必要です。

### 3. championはnullになりうる

`Leaderboard.champion`の型は`LeaderboardRow | None`です。多重比較補正後にベースラインを有意に上回るモデルがなければ`NO_MODEL_BEATS_BASELINE / champion=null`を返します。

### 4. リークは反証可能

研究実行ではラベル置換・時間シフト・厳密因果監査を実施します。Timer Base 84M OOF foundationではtarget contextを対象drawより前に限定し、prediction recordを実測参照前にimmutable write + SHA-256 sealします。

### 5. Runtime certificationはavailability表示と別物

load、input、inference、output shape、finite values、device、GPU PID/VRAM、CPU fallbackを実測して初めてruntime evidenceとします。

## 理論限界

[`docs/THEORETICAL_BOUNDS.md`](docs/THEORETICAL_BOUNDS.md)（`loto3 theory`で再生成）。MAE下限と±1上限は別目的であり、同時最適化できない場合があります。formal比較ではPrimary KPIをHit@±1として固定し、MAE/MSE/RMSEを併記します。

## Current certification boundary

確認済み:

- PR #240の実装・テスト・Windows portability・資料は`main`へmerge済み
- Windows focused validation 20/20 PASS
- standard CI / windows-portability-ciはmerge前current headでSUCCESS
- Holdout actuals opened=false
- Prospective actuals opened=false
- formal OOF run=false
- Timer inference run=false

未完了または未認定:

- 新PC上の正式development-only data source setup
- immutable development snapshotの生成・検証
- Windows上でのfinal `EvaluationProtocolV2`固定
- formal baseline OOF
- formal Timer Base 84M OOF
- 複数seed mean / variance / worst集約
- Holdout開封とProspective評価
- champion / promotion

## v3.2.0: All-model / all-setting bounded auto coverage research

Native Windowsでは次のPowerShell entrypointを使用できます。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_auto_coverage_loop.ps1 -AcquireData
```

このsearchは`parameter_spaces`へ明示された有限Cartesian product、宣言済みensemble、±1 row coverageを満たすためのbounded candidate setを対象にします。必要に応じてOpenAI-compatible local LLMへ追加proposalを依頼できますが、protected testをtuningへ使わず、validationで90%へ到達していない限り90%を報告しません。

"all settings"はYAMLで宣言した有限探索空間を意味し、全実数値・全architectureを意味しません。

## ライセンスと免責

本ソフトウェアは時系列予測手法の**研究**を目的とします。宝くじの当選を予測する能力は主張しません。正式な性能主張は、固定済みprotocol、リーク検査、baseline比較、multi-seed集約、prediction sealingを通過したevidenceだけを根拠にします。
