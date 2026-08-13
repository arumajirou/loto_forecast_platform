# Library / Model Compatibility Matrix

この文書は、Loto Forecast Platform のモデル実装を **ライブラリ単位** で確認するための対応表です。

README の全体像に対して、本書は次の質問へ素早く答えることを目的にします。

1. そのライブラリには何モデル登録されているか。
2. どのモデルが shared route / provider / isolated campaign から実行できるか。
3. どの主要引数・機能を扱うか。
4. runtime / OOF / Holdout / Prospective の証拠はどこまであるか。
5. 「登録済み」と「正式に科学評価済み」を混同していないか。

> **Audit basis:** `main@4f4f8579c6bcc05e25ea472e48385114bb56c71d` / 2026-08-13  
> **Primary code sources:** `src/loto/models/catalog_full.py`, `src/loto/models/catalog.py`, `src/loto/models/implementation_catalog.py`, framework/provider implementations, tests, retained runtime evidence  
> **Current execution addenda:** `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md`, `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`  
> **Rule:** `REGISTERED != ROUTABLE != RUNTIME_CERTIFIED != OOF_EVALUATED != HOLDOUT_EVALUATED != PROSPECTIVE_EVALUATED != PROMOTION_ELIGIBLE`

---

## 1. 状態の読み方

| 状態 | 意味 |
|---|---|
| `REGISTERED` | catalog / source inventory に identity がある |
| `SHARED_ROUTABLE` | 通常 shared execution surface から選択できる |
| `PROVIDER_ROUTABLE` | provider / isolated process 経路がある |
| `RUNTIME_CERTIFIED` | exact identity で load / inference / shape / finite / device 等の正式証拠がある |
| `PARTIAL_RUNTIME_EVIDENCE` | 一部環境・一部モデル・一部証拠だけが成立 |
| `OPERATOR_LOCAL_EVIDENCE` | maintainer hostで得たexact-source証拠。current-main retained certificationとは別クラス |
| `OOF_EVALUATED` | chronological development OOF が完了 |
| `EXECUTION_PENDING` | 実装・計画はあるが対象分母を完走していない |
| `BLOCKED` | runner / dependency / license / artifact / policy 等で明示的に停止 |

**重要:** import 成功、`available=true`、モデル名登録、単一 smoke 成功だけでは `RUNTIME_CERTIFIED` としません。operator-local exact-source PASSも、より新しいmain SHAのformal certificationへ自動昇格しません。

---

## 2. ライブラリ別サマリー

### 2.1 Broad v1 = 174 の内訳

`catalog_full.py` の current code から導出される Broad v1 の内訳です。Broad v1は凍結された分母で、dynamic / Expanded v2のidentityを足し戻しません。

| Library | Broad v1 count | 主な役割 | shared / provider の実態 | 現在の証拠状態 |
|---|---:|---|---|---|
| builtin | 4 | theory / frequency controls | shared | **VERIFIED** |
| scikit-learn | 7 | candidate / position ML | shared | **VERIFIED / PARTIALLY_VERIFIED** |
| LightGBM | 2 | candidate / position boosting | shared | **OPENCL GPU ROUTE VERIFIED / CUDA NOT CERTIFIED** |
| XGBoost | 1 | candidate boosting | shared | **CUDA GPU ROUTE VERIFIED** |
| CatBoost | 1 | candidate boosting | shared | **GPU ROUTE VERIFIED** |
| StatsForecast | 41 | statistical forecasting | broad 41 / shared explicit 8 | **VERIFIED / PARTIALLY_VERIFIED** |
| NeuralForecast fixed | 37 | deep forecasting | broad 37 / direct shared subset 17 | **VERIFIED / PARTIALLY_VERIFIED** |
| NeuralForecast Auto | 36 | HPO deep forecasting | dedicated AutoModel execution surface | **VERIFIED / PARTIALLY_VERIFIED** |
| MLForecast Auto | 8 | lag-based AutoML | broad Auto 8 / direct shared 2 | **PARTIALLY_VERIFIED** |
| HierarchicalForecast | 10 | reconciliation | reconciliation surface | **VERIFIED / PARTIALLY_VERIFIED** |
| TSFM | 21 | foundation / zero-shot | shared provider subset + isolated lanes | retained audit **19 runtime CERTIFIED / 2 BLOCKED** |
| AutoGluon TimeSeries | 1 umbrella | AutoML / ensemble | isolated provider; Expanded v2 decomposes to 37 | **PARTIALLY_VERIFIED** |
| Darts | 1 | ensemble framework | shared optional lane | **PARTIALLY_VERIFIED** |
| GluonTS | 1 | probabilistic DeepAR | shared optional lane | **PARTIALLY_VERIFIED** |
| ReservoirPy | 1 | ESN | shared optional lane | **PARTIALLY_VERIFIED** |
| sktime | 1 | forecasting framework | isolated campaign | **PARTIALLY_VERIFIED**; P1 fixed 4-model formal PASS on exact source |
| skforecast | 1 | recursive lag ML | Broad identity remains one entry; Expanded integration open | **PARTIALLY_VERIFIED / OPERATOR_LOCAL_EVIDENCE** |
| **TOTAL** | **174** |  |  | Broad denominator is frozen |

### 2.2 Broad v1 外の主要 framework / dynamic denominators

| Framework / inventory | Broad v1 への収録 | 実装面 | 現在状態 |
|---|---|---|---|
| scikit-learn dynamic | outside 174 | `loto-sklearn` installed-version discovery/certification | **PROVIDER VERIFIED / estimator runtime varies** |
| sktime registry | outside Broad denominator | isolated registry/campaign | **141 discovered/importable; not 141 runtime-certified** |
| Expanded v2 Phase 1 | separate inventory | implementation catalog | **210 identities** |
| Time-Series-Library | outside 174 | isolated campaign / provider | **PARTIALLY_VERIFIED** |
| BasicTS | outside 174 | isolated campaign / provider | **PARTIALLY_VERIFIED** |
| Merlion | outside 174 | isolated runtime/certification lane | **EXECUTION_PENDING** for target-host completion |
| Probabilistic platform | separate catalog | `loto3 probabilistic` | **VERIFIED / PARTIALLY_VERIFIED** |

---

## 3. 共通機能対応表

| Library / family | Candidate | Position | Position-series | Exogenous | Probabilistic | GPU path | HPO | Reconciliation | Shared route | Isolated/provider |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| builtin | ✓ | ✓ | — | — | 一部 | — | — | — | ✓ | — |
| scikit-learn | ✓ | ✓ | ✓ | ✓ | classifier系 | CPU中心 / tree別 | — | — | ✓ | dynamic providerもあり |
| LightGBM | ✓ | — | ✓ | ✓ | classifier | **OpenCL GPU verified** | — | — | ✓ | — |
| XGBoost | ✓ | — | — | ✓ | classifier | **CUDA verified** | — | — | ✓ | — |
| CatBoost | ✓ | — | — | ✓ | classifier | **GPU verified** | — | — | ✓ | — |
| StatsForecast | 一部 | — | ✓ | model依存 | conformal等 | CPU中心 | model内Auto | — | 8 explicit | campaign |
| MLForecast | — | — | ✓ | ✓ | regressor依存 | backend依存 | ✓ | — | 2 direct | research/AutoML |
| NeuralForecast fixed | — | — | ✓ | model依存 | model依存 | ✓ | — | 一部 | 17 direct | dedicated paths |
| NeuralForecast Auto | — | — | ✓ | base model依存 | base model依存 | ✓ | Ray / Optuna | 一部 | specあり | dedicated AutoModel runner |
| AutoGluon | — | — | ✓ | model依存 | ✓ | backend依存 | AutoML | ensemble | umbrella | ✓ isolated |
| Darts | — | — | ✓ | framework依存 | ✓ | optional | — | — | ✓ | optional |
| GluonTS | — | — | ✓ | estimator依存 | ✓ | current shared path CPU-pinned | — | — | ✓ | optional |
| ReservoirPy | — | ✓ | — | — | — | CPU中心 | — | — | ✓ | optional |
| HierarchicalForecast | — | — | base forecast入力 | — | — | — | — | ✓ | reconciliation | optional |
| sktime | — | — | ✓ | estimator依存 | estimator依存 | estimator依存 | estimator依存 | 一部 | — | ✓ |
| skforecast | — | — | ✓ | ✓ | bootstrap/conformal/foundation model依存 | estimator/foundation依存 | grid/random/Optuna等 | — | Broad exact route未完 | upstream wrapper/runtime surfaceをoperator検証 |
| TSFM | TabPFN-TS等 | — | ✓ | model依存 | model依存 | 多くはGPU検証対象 | — | — | subset | ✓ |
| Time-Series-Library | — | — | ✓ | architecture依存 | architecture依存 | ✓ | project側で可能 | — | — | ✓ |
| BasicTS | — | — | ✓ | framework依存 | framework依存 | framework依存 | framework依存 | — | — | ✓ |

`✓` は capability / execution surface が存在することを示し、全モデルで正式認証済みという意味ではありません。

---

## 4. builtin / scikit-learn / boosting

### 4.1 builtin

| model_id | class / semantics | task | 主な役割 | 状態 |
|---|---|---|---|---|
| `uniform` | `UniformCandidateAdapter` | candidate | theoretical uniform control | **VERIFIED** |
| `frequency` | `FrequencyCandidateAdapter` | candidate | frequency baseline | **VERIFIED** |
| `position-median` | `TheoryMedianAdapter` | position | MAE-floor control | **REGISTERED** in Broad |
| `position-modal` | `TheoryModalAdapter` | position | within-tau ceiling control | **REGISTERED** in Broad |

### 4.2 scikit-learn Broad 7

| Broad model_id | shared route | class | 主な default params / capability |
|---|---|---|---|
| `logistic` | `logistic` | LogisticRegression | `C=1.0`, `max_iter=1000`, probability, exogenous |
| `ridge` | `ridge-position` | Ridge | `alpha=1.0`, position, exogenous |
| `elastic-net` | `elasticnet-position` | ElasticNet | `alpha=0.01`, `l1_ratio=0.5`, `max_iter=5000` |
| `random-forest` | `random-forest` | RandomForestClassifier | `n_estimators=300`, `min_samples_leaf=3`, `n_jobs=-1` |
| `extra-trees` | `extra-trees` | ExtraTreesClassifier | `n_estimators=300`, `min_samples_leaf=2`, `n_jobs=-1` |
| `hist-gradient-boosting` | `hist-gradient-boosting` | HistGradientBoostingClassifier | `learning_rate=0.05`, `max_iter=200` |
| `isotonic-calibrated-logistic` | dedicated calibration route | CalibratedClassifierCV | `method=isotonic`, `cv=3`; routing gap repaired in #303 |

Dynamic all-estimator provider is a separate denominator exposed by `loto-sklearn`; it does not alter Broad 7 or Broad total 174.

### 4.3 LightGBM / XGBoost / CatBoost

| Library | model_id | class | task | major defaults | current runtime boundary |
|---|---|---|---|---|---|
| LightGBM | `lightgbm-classifier` | LGBMClassifier | candidate | `n_estimators=400`, `learning_rate=0.03`, `num_leaves=31` | OpenCL `device_type="gpu"` route verified; CUDA tree learner not certified |
| LightGBM | `lightgbm-position` | LGBMRegressor | position-series | `n_estimators=400`, `learning_rate=0.03` | same OpenCL contract |
| XGBoost | `xgboost-classifier` | XGBClassifier | candidate | `n_estimators=400`, `learning_rate=0.03`, `max_depth=5` | scheduler GPU lease → CUDA route verified |
| CatBoost | `catboost-classifier` | CatBoostClassifier | candidate | `iterations=400`, `learning_rate=0.03` | scheduler GPU lease → GPU route verified |

---

## 5. StatsForecast — 41 models

### 5.1 全41モデルをfamily別に整理

| family | models | count |
|---|---|---:|
| ARIMA / autoregressive | AutoARIMA, ARIMA, AutoRegressive | 3 |
| exponential smoothing | AutoETS, AutoCES, SimpleExponentialSmoothing, SimpleExponentialSmoothingOptimized, SeasonalExponentialSmoothing, SeasonalExponentialSmoothingOptimized, Holt, HoltWinters | 8 |
| Theta | AutoTheta, Theta, OptimizedTheta, DynamicTheta, DynamicOptimizedTheta | 5 |
| intermittent | ADIDA, CrostonClassic, CrostonOptimized, CrostonSBA, IMAPA, TSB | 6 |
| decomposition / complex statistical | AutoMFLES, AutoTBATS, MSTL, MFLES, TBATS, UCM | 6 |
| baseline / control | HistoricAverage, Naive, RandomWalkWithDrift, SeasonalNaive, WindowAverage, SeasonalWindowAverage, ConstantModel, ZeroModel, NaNModel | 9 |
| conformal | ConformalSeasonalPool | 1 |
| volatility | GARCH, ARCH | 2 |
| wrapper | SklearnModel | 1 |
| **TOTAL** |  | **41** |

### 5.2 shared route 8

| shared model_id | StatsForecast class | task semantics | current interpretation |
|---|---|---|---|
| `stats-naive` | Naive | position-series | shared |
| `stats-historic-average` | HistoricAverage | position-series | shared |
| `stats-autoarima` | AutoARIMA | position-series | shared |
| `stats-autoets` | AutoETS | position-series | shared |
| `stats-autotheta` | AutoTheta | position-series | shared |
| `stats-autoces` | AutoCES | position-series | shared |
| `stats-croston` | CrostonClassic | candidate-series | intermittent semantics |
| `stats-tsb` | TSB | candidate-series | intermittent semantics |

### 5.3 実装状態

| 項目 | status |
|---|---|
| source / Broad inventory 41 | **VERIFIED** |
| shared explicit 8 | **VERIFIED** |
| runtime lifecycle certification machinery | **VERIFIED / PARTIALLY_VERIFIED** |
| property lifecycle evidence | **VERIFIED / PARTIALLY_VERIFIED** |
| real-game development evaluation lane | **VERIFIED / PARTIALLY_VERIFIED** |
| 41 × 6 全モデル全ゲーム完走 | **EXECUTION_PENDING** |
| blanket OOF superiority claim | **NOT ESTABLISHED** |

---

## 6. MLForecast — Auto 8 + direct shared 2

### 6.1 Auto inventory 8

| AutoModel | backend estimator family | Broad status | direct shared route |
|---|---|---|---|
| AutoLightGBM | LightGBM | `REGISTERED` | no dedicated Auto shared ID |
| AutoXGBoost | XGBoost | `REGISTERED` | no |
| AutoCatboost | CatBoost | `REGISTERED` | no |
| AutoLinearRegression | linear | `REGISTERED` | no |
| AutoRidge | Ridge | `REGISTERED` | related direct `mlforecast-ridge` |
| AutoLasso | Lasso | `REGISTERED` | no |
| AutoElasticNet | ElasticNet | `REGISTERED` | no |
| AutoRandomForest | RandomForest | `REGISTERED` | no |

Broad Auto entries use AutoMLForecast semantics with upstream default search spaces. They are not eight independent shared workers.

### 6.2 direct shared paths

| model_id | estimator | capabilities |
|---|---|---|
| `mlforecast-ridge` | Ridge | lags, exogenous |
| `mlforecast-lightgbm` | LGBMRegressor | lags, exogenous, GPU optional |

---

## 7. NeuralForecast fixed — 37 models

### 7.1 family別一覧

| family | models | count |
|---|---|---:|
| RNN | RNN, GRU, LSTM, DilatedRNN, xLSTM | 5 |
| CNN | TCN, BiTCN | 2 |
| deep probabilistic | DeepAR, DeepNPTS | 2 |
| MLP | MLP, NBEATS, NBEATSx, NHITS, MLPMultivariate, TiDE | 6 |
| linear | DLinear, NLinear, XLinear | 3 |
| transformer | TFT, VanillaTransformer, Informer, Autoformer, FEDformer, PatchTST, iTransformer, TimesNet, TimeXer, TimeLLM | 10 |
| mixer | TSMixer, TSMixerx, SOFTS, SOFTSSharp, TimeMixer | 5 |
| KAN | KAN, RMoK | 2 |
| graph | StemGNN | 1 |
| hierarchical | HINT | 1 |
| **TOTAL** |  | **37** |

### 7.2 direct shared subset 17

| model | shared model_id | broad capability notes |
|---|---|---|
| DLinear | `nf-dlinear` | GPU, checkpoint |
| NLinear | `nf-nlinear` | GPU, checkpoint |
| NHITS | `nf-nhits` | GPU, checkpoint; shared spec also marks exogenous |
| NBEATS | `nf-nbeats` | GPU, checkpoint |
| NBEATSx | `nf-nbeatsx` | GPU, checkpoint, exogenous |
| TiDE | `nf-tide` | GPU, checkpoint, exogenous |
| TCN | `nf-tcn` | GPU, checkpoint |
| GRU | `nf-gru` | GPU, checkpoint |
| LSTM | `nf-lstm` | GPU, checkpoint |
| DeepAR | `nf-deepar` | GPU, probabilistic |
| TFT | `nf-tft` | GPU, exogenous, attention |
| PatchTST | `nf-patchtst` | GPU |
| TimesNet | `nf-timesnet` | GPU; FFT family precision constraint applies |
| TSMixer | `nf-tsmixer` | GPU, multiseries |
| TimeMixer | `nf-timemixer` | GPU; FFT family precision constraint applies |
| iTransformer | `nf-itransformer` | GPU, multivariate |
| VanillaTransformer | `nf-vanilla-transformer` | GPU |

### 7.3 Broad capability sets

| capability | models |
|---|---|
| exogenous | NBEATSx, TFT, TSMixerx, TimeXer, BiTCN, TiDE |
| probabilistic | DeepAR, DeepNPTS, TFT, HINT |
| multivariate / requires `n_series` | StemGNN, MLPMultivariate, TSMixer, TSMixerx, SOFTS, SOFTSSharp, TimeMixer, RMoK, iTransformer |
| FFT / force full precision | TimesNet, FEDformer, Autoformer, TimeMixer |

**37 registered** と **37 all runtime-certified** は同義ではありません。

---

## 8. NeuralForecast AutoModels — official 36

### 8.1 official inventory

| family | AutoModels |
|---|---|
| RNN | AutoRNN, AutoLSTM, AutoGRU, AutoDilatedRNN, AutoxLSTM |
| CNN | AutoTCN, AutoBiTCN |
| deep probabilistic | AutoDeepAR, AutoDeepNPTS |
| MLP | AutoMLP, AutoNBEATS, AutoNBEATSx, AutoNHITS, AutoTiDE, AutoMLPMultivariate |
| linear | AutoDLinear, AutoNLinear, AutoXLinear |
| transformer | AutoTFT, AutoVanillaTransformer, AutoInformer, AutoAutoformer, AutoFEDformer, AutoPatchTST, AutoiTransformer, AutoTimeXer, AutoTimesNet |
| graph | AutoStemGNN |
| hierarchical | AutoHINT |
| mixer | AutoTSMixer, AutoTSMixerx, AutoSOFTS, AutoSOFTSSharp, AutoTimeMixer |
| KAN | AutoKAN, AutoRMoK |

### 8.2 共通HPO / runtime controls

| type | argument / control | repository interpretation |
|---|---|---|
| horizon | `h` | forecast horizon |
| objective | `loss`, `valid_loss` | train / validation objectives |
| search space | `config` | official per-model defaults or explicit custom config |
| backend | `backend` | Ray / Optuna |
| search | `search_alg` / search strategy | backend整合性をfail-closedで検証 |
| budget | `num_samples` | trial count |
| resources | `cpus`, `gpus`, trial parallelism | resource-aware execution |
| reproducibility | `random_seed` / CLI seed | experiment control; HPO dimensionへ自動変換しない |
| precision | repository `precision` | actual fitted model/trainerへ伝播 |
| refit | `refit_with_val` | best model refit policy |
| observability | callbacks / training evidence | GPU training, pre-save, reload evidenceと接続 |

Merged implementationでは、official default search spaceを保持したまま fixed experiment controls を overlayし、seed / precision、multiseries `n_series`、early-stop、GPU training evidence を扱います。

### 8.3 local extensions

| extension | status |
|---|---|
| AutoTimeLLM | fail-closed local extension |
| AutoSCINet | local extension |
| AutoSegRNN | inactive |
| AutoFreTS | inactive |

---

## 9. AutoGluon TimeSeries — Expanded v2 Phase 1

Broad v1では `autogluon-timeseries` 1 umbrella entryです。Expanded v2 Phase 1では source-backed identity に分解します。

### 9.1 source models 29

| category | models | count |
|---|---|---:|
| intermittent | ADIDA, Croston, IMAPA | 3 |
| statistical | ARIMA, AutoARIMA, AutoCES, AutoETS, DynamicOptimizedTheta, ETS, Theta | 7 |
| baseline | Average, Naive, SeasonalAverage, SeasonalNaive, Zero | 5 |
| deep learning | DLinear, PatchTST, SimpleFeedForward, TiDE | 4 |
| deep probabilistic | DeepAR, TemporalFusionTransformer, WaveNet | 3 |
| tabular | DirectTabular, PerStepTabular, RecursiveTabular | 3 |
| foundation | Chronos, Chronos2, Toto | 3 |
| nonparametric | NPTS | 1 |
| **TOTAL** |  | **29** |

### 9.2 unique ensemble classes 8

| ensemble | notes |
|---|---|
| Greedy | canonical greedy ensemble |
| PerItemGreedy | per-item greedy |
| PerformanceWeighted | performance-weighted |
| SimpleAverage | simple average |
| Median | median ensemble |
| Tabular | tabular ensemble |
| PerQuantileTabular | quantile-specific tabular ensemble |
| LinearStacker | linear stacking |

`Weighted` は `GreedyEnsemble` alias なので unique class count には重複加算しません。

### 9.3 status boundary

| item | status |
|---|---|
| Broad umbrella | 1 |
| source models | 29 |
| unique ensemble classes | 8 |
| Expanded AutoGluon identities | 37 |
| Expanded v2 total after replacement | `174 - 1 + 37 = 210` |
| default `runtime_status` | `NOT_RUN` |
| default `runtime_certified` | `False` |
| all 37 runtime-certified | **NO / EXECUTION_PENDING** |

---

## 10. HierarchicalForecast — 10 reconciliation methods

| method | role | standalone forecaster? |
|---|---|:---:|
| BottomUp | bottom-up reconciliation | no |
| BottomUpSparse | sparse bottom-up | no |
| TopDown | top-down reconciliation | no |
| TopDownSparse | sparse top-down | no |
| MiddleOut | middle-out reconciliation | no |
| MiddleOutSparse | sparse middle-out | no |
| MinTrace | minimum-trace reconciliation | no |
| MinTraceSparse | sparse MinTrace | no |
| OptimalCombination | optimal combination reconciliation | no |
| ERM | empirical risk minimization reconciliation | no |

これらは base forecast を coherent に変換する reconciliation methods であり、10個の独立予測モデルとして精度比較してはいけません。

---

## 11. TSFM / foundation models — 21 retained runtime audit identities

Retained runtime audit の current interpretation は **19 CERTIFIED / 2 BLOCKED / 0 pending** です。ただし runtime certification は lottery-domain compatibility や OOF accuracy を意味しません。

| audit identity | runtime | shared/provider relation | important boundary |
|---|---|---|---|
| chronos-2 | CERTIFIED | shared exact ID / ChronosProvider | runtime ≠ OOF |
| chronos-bolt-tiny | CERTIFIED | shared exact ID / ChronosProvider | runtime ≠ OOF |
| chronos-t5-small | CERTIFIED | shared exact ID / ChronosProvider | runtime ≠ OOF |
| chronos-t5-base | CERTIFIED | exact shared ModelSpecなし | provider/routing scope別 |
| granite-flowstate-r1 | CERTIFIED | exact shared ModelSpecなし | routing別 |
| granite-patchtsmixer | CERTIFIED | exact shared ModelSpecなし | routing別 |
| granite-patchtst | CERTIFIED | exact shared ModelSpecなし | routing別 |
| granite-ttm-r2 | CERTIFIED | shared `granite-ttm`とはidentity差 | exact identity binding必須 |
| kronos-base | CERTIFIED | dedicated provider script | native financial OHLCV; lottery compatibility=false |
| lag-llama | CERTIFIED | exact shared ModelSpecなし | shared research routing別 |
| moirai-1.0-base | **BLOCKED** | exact shared specなし | weights missing; personal/noncommercial scope |
| moirai-2.0-small | CERTIFIED | shared `moirai`とidentity差 | retained identity evidence; separate skforecast dependency issue below |
| moment-1-large | CERTIFIED | exact shared ModelSpecなし | forecasting head scope確認必要 |
| moment-1-small | CERTIFIED | exact shared ModelSpecなし | forecasting head scope確認必要 |
| sundial-base | CERTIFIED | shared `sundial`とidentity差 | exact identity binding必須 |
| t0-alpha | **BLOCKED** | shared runnable specなし | retained audit gated access required |
| tabpfn-ts | CERTIFIED | retained shared exact ID | do not inherit this into new TS-3 lane automatically |
| timesfm-2.5-transformers | CERTIFIED | shared `timesfm-2.5`とidentity差 | exact package/revision確認 |
| tirex-2 | CERTIFIED | shared `tirex`とlogical ID差 | exact identity確認 |
| toto-2.0-4m | CERTIFIED | exact shared registry entryなし | dedicated runtime evidence |
| toto-open-base | CERTIFIED | exact shared registry entryなし | dedicated runtime evidence |

### Toto 2.0 22M current gate

PR #296 の 22M path は pinned snapshot と CUDA load/inference/replay evidence を持ちますが、正式 native-Linux external PID / VRAM / release gate は未完です。

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
Holdout=CLOSED
Prospective=CLOSED
automatic promotion=FORBIDDEN
```

---

## 12. Darts / GluonTS / ReservoirPy / sktime / skforecast

| Library | Broad identity | implementation | main parameters / notes | current status |
|---|---|---|---|---|
| Darts | `darts-ensemble` | RegressionEnsembleModel | NaiveDrift + ExponentialSmoothing ensemble lane | **PARTIALLY_VERIFIED** |
| GluonTS | `gluonts-deepar` | DeepAREstimator | shared defaults include `epochs=1`, `num_batches_per_epoch=2`, `context_length=16`, `num_samples=20`; shared path CPU-pinned | **PARTIALLY_VERIFIED** |
| ReservoirPy | `reservoir-esn` | ESN / Reservoir + Ridge | `reservoir_size=50`, `spectral_radius=0.9`, `leak_rate=0.3`, `ridge_alpha=1e-6` | **PARTIALLY_VERIFIED** |
| sktime | `sktime-ensemble` | EnsembleForecaster / isolated campaign | registry 141 discovered/importable; P1 fixed four-model formal matrix passed | **PARTIALLY_VERIFIED / Expanded v2 still open** |
| skforecast | `skforecast-recursive` | ForecasterRecursive Broad identity | root optional dep declares `skforecast>=0.17`; operator runtime used 0.23.0 | **PARTIALLY_VERIFIED / OPERATOR_LOCAL_EVIDENCE / repository routing pending** |

### 12.1 sktime evidence boundary

Current exact-source P1 evidence:

```text
sktime=1.0.1
registry discovered=141
registry importable=141
core-compatible=53
optional-dependency-declared=88
formal P1 models=4
4/4 construct/fit/predict/finite/save-load/re-predict/formal verification=PASS
```

This does not convert 141 discovered/importable forecasters into 141 runtime-certified implementations. #289 / TAJ-32 remains open.

### 12.2 skforecast 0.23.0 operator-local evidence

The maintainer-host sequence was run against exact source head:

```text
9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd
```

This is an `OPERATOR_LOCAL_EVIDENCE` class, not current-main retained certification.

#### Core strategies / estimator integration

Observed PASS after correcting two smoke-harness assumptions:

- `ForecasterRecursive + Ridge + exog`;
- `ForecasterRecursive + HistGradientBoostingRegressor`;
- recursive LightGBM / XGBoost / CatBoost CPU smoke;
- `ForecasterDirect + Ridge`;
- `ForecasterRecursiveMultiSeries`;
- `ForecasterDirectMultiVariate + Ridge`;
- `ForecasterEquivalentDate`;
- `ForecasterStats + ARAR`;
- RollingFeatures / CalendarFeatures;
- TimeSeriesFold/backtesting;
- Optuna Bayesian search;
- save/load exact prediction round trip;
- RangeDriftDetector;
- bootstrap and out-of-sample calibrated interval paths.

The initial multi-series expected-length failure and bootstrap residual-storage failure were harness/config mistakes, not library runtime defects.

#### RNN

| implementation | GPU | CPU fallback | device evidence |
|---|---:|---:|---|
| ForecasterRnn LSTM | PASS | PASS | CUDA model variables + PyTorch allocation + external PID; CPU zero-CUDA proof |
| ForecasterRnn GRU | PASS | not repeated in this sequence | CUDA model variables + allocation + external PID |

#### Foundation adapters

| implementation | operator-local runtime | exog | probabilistic surface | boundary |
|---|---|:---:|---|---|
| Chronos-2 small | **GPU + CPU PASS** | ✓ | native interval | HF revision observed; repository revision enforcement/routing separate |
| TimesFM 2.5 | **GPU + CPU PASS** | — | interval + q0.1/q0.5/q0.9 | source revision recorded; adapter correctly no-exog |
| Moirai-2 small | **GPU + CPU PASS under controlled override** | — | interval + quantiles | normal dependency metadata conflict keeps routability BLOCKED |
| TabICL v2 | **GPU + CPU PASS** | ✓ | interval + quantiles | checkpoint revision/bytes/SHA-256 VERIFIED |
| TabPFN-TS v3 path | adapter/device setup PASS | ✓ | not executed | invalid/expired Prior Labs token blocks V3 weight download/inference |
| T0 | not run | model-dependent | not run | pending in this sequence |

TabICL artifact identity:

```text
repo=jingang/TabICL
revision=4dcd344ece2c00be9e831fdd35bed57b5ad83e19
checkpoint=tabicl-regressor-v2-20260212.ckpt
size_bytes=114324594
sha256=0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a
status=VERIFIED
```

TabPFN-TS current operator diagnostic:

```text
tabpfn-time-series=1.2.0
tabpfn=8.1.0
requested_checkpoint=tabpfn-v3-regressor-v3_20260506_timeseries.ckpt
license_name=tabpfn-3-license-v1.0
token_valid=false
license_accepted=not evaluated
runtime_inference=NOT_EXECUTED
```

A cached `TabPFN-v2-reg` checkpoint is a different identity and must not be used as TS-3 evidence.

Full details: `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`.

#### Expanded v2 interpretation

The operator evidence does not define the final skforecast Expanded v2 count. #289 / TAJ-32 still must:

- distinguish `algorithm_id` from `implementation_id`;
- avoid wrapper × estimator Cartesian inflation;
- freeze source/revision-backed implementation identities;
- attach routability/capability/resource metadata;
- add focused committed construct/predict tests;
- preserve blocked/non-routable identities explicitly;
- keep Broad v1=174 unchanged.

---

## 13. Time-Series-Library / BasicTS / Merlion

| Framework | repository surface | currently named models / role | status boundary |
|---|---|---|---|
| Time-Series-Library | isolated `time_series_library_campaign` | DLinear, TSMixer, LightTS, SegRNN, FreTS, SCINet, TimeFilter, TiDE, FiLM | campaign/provider exists; upstream全architecture certificationではない |
| BasicTS | isolated `basicts_campaign` | provider/config/dataset/runtime smoke contracts | framework-wide runtime certificationではない |
| Merlion | isolated `merlion_campaign` | ARIMA, ETS, MSES | target-host completion pending |

---

## 14. 引数・リソース・科学評価の横断対応

### 14.1 実行制御

| control | 主に関係するlibrary | purpose |
|---|---|---|
| game / geometry | all | output width / legal value contract |
| seed | all stochastic models | reproducibility; best-seed-only adoption禁止 |
| horizon `h` | forecasting libraries | forecast length |
| CPU / GPU allocation | NF, AutoNF, boosting, TSFM, isolated providers | resource planning |
| precision | NF / AutoNF / GPU models | `32-true`等; FFT modelsはfull precision制約 |
| trial count | AutoNF / AutoML / skforecast search | HPO budget |
| backend | AutoNF | Ray / Optuna |
| timeout | campaigns/providers | runaway process prevention |
| save/reload | trainable models | lifecycle certification |
| revision / repo_id | TSFM / foundation adapters | exact identity reproducibility |
| license/auth | gated models | access/governance gate; runtime failureと分離 |

### 14.2 科学評価

| gate | required evidence |
|---|---|
| Development OOF | chronological folds, Train-only preprocessing/HPO, all seeds |
| Primary metric | **Hit@±1** |
| Secondary metrics | MAE, MSE, RMSE, position-wise Hit@±1, all-position Hit@±1 |
| Baselines | Random, fixed, mean, median, recent, frequency, statistical |
| Prediction lock | actual判明前のSHA-256 + timestamp |
| Holdout | explicit authorization only |
| Prospective | sealed future prediction + later actual |
| Promotion | human approval; automatic promotion forbidden |

Synthetic smoke metrics in runtime certification are diagnostics only and are not substituted for development OOF.

---

## 15. どこまで実装されているかを確認する順序

ライブラリやモデル名がこの表にあるだけで成功扱いにしないでください。確認順序は次です。

```text
source-declared
  -> catalog-registered
  -> shared/provider-routable
  -> dependency/version/identity verified
  -> load verified
  -> input accepted
  -> inference executed
  -> output shape / finite verified
  -> device / GPU PID / VRAM / CPU fallback verified
  -> save/reload verified when applicable
  -> runtime-certified
  -> lottery-compatible
  -> chronological OOF evaluated
  -> Holdout evaluated
  -> Prospective evaluated
  -> promotion eligible
  -> human approval
```

---

## 16. 関連コマンド

```bash
# Broad v1 counts / inventory
uv run loto3 catalog --counts
uv run loto3 catalog

# shared ModelSpec surface
uv run loto models list

# full model × game plan only
uv run loto3 campaign --output unused --plan-only

# parallel Unified Campaign
uv run python -m loto.evaluation.parallel_campaign --help

# dynamic sklearn provider
uv run loto-sklearn list
uv run loto-sklearn smoke --model RandomForestRegressor --seed 1
uv run loto-sklearn certify --kind all --seed 1 --output artifacts/sklearn-certification

# sktime P1
ROOT="$PWD" SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p1_matrix_certification.sh

# NeuralForecast AutoModels
uv run loto neuralforecast automodel-run --help

# TSFM revisions
uv run loto3 revisions --help

# probabilistic catalog
uv run loto3 probabilistic catalog-list
uv run loto3 probabilistic backends
```

---

## 17. Source of truth

1. current code
   - `src/loto/models/catalog_full.py`
   - `src/loto/models/catalog.py`
   - `src/loto/models/implementation_catalog.py`
   - `src/loto/models/providers.py`
   - framework-specific campaign / provider modules
2. tests / workflows / repository-retained evidence
3. exact-source operator/local runtime evidence with environment provenance
4. merged PR / commit history
5. live GitHub Issues / Linear project state
6. current documentation
7. historical snapshots

関連資料:

- `README.md`
- `docs/STATUS.md`
- `docs/CURRENT_VERIFICATION_REPORT.md`
- `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md`
- `docs/SKFORECAST_RUNTIME_CERTIFICATION.md`
- `docs/CAPABILITIES_AND_OPERATIONS.md`
- `docs/TSFM_RUNTIME_CAPABILITIES.md`
- `docs/evaluation/`
- `docs/operations/`

Holdout remains **CLOSED**. Prospective remains **CLOSED**. Automatic promotion remains **FORBIDDEN**.
