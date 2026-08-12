# Loto Forecast Platform

**ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4**を対象に、統計モデル、機械学習、深層学習、AutoML、時系列基盤モデル（TSFM）、確率モデルを、時系列リークを防いだ共通契約の下で比較・検証・運用する研究プラットフォームです。

このREADMEは、単なる「登録モデル一覧」ではなく、**何がコードとして存在し、どこから実行でき、どこまで実測証拠があり、何がまだ未検証か**を区別して読むための入口です。

> **Implementation audit base:** `main@abe7e02cdfc900618c83b21c922b4fd3f078b036` (2026-08-12)  
> **Fact-check sources:** current `main` code / merged PR history / tests / retained runtime artifacts / Linear project state  
> **Important:** `REGISTERED != RUNTIME_CERTIFIED != OOF_EVALUATED != HOLDOUT_EVALUATED != PROSPECTIVE_EVALUATED != PROMOTION_ELIGIBLE`

---

## 1. 現在地 — 先に結論

| 領域 | 現在状態 | 事実として確認できること | まだ意味しないこと |
|---|---|---|---|
| 6ゲーム共通geometry | **VERIFIED** | `mini/loto6/loto7/bingo5/numbers3/numbers4` のpositions・値域・select/digits契約あり | 全モデルが6ゲームで実測済み、ではない |
| Broad v1 inventory | **VERIFIED** | `catalog_full.py` の凍結在庫 **174** | 174モデルすべてruntime成功、ではない |
| Unified v1 coverage | **EXECUTION_PENDING** | 既存計画の分母 **250 × 6 = 1500 units** | 1500 unit完走済み、ではない |
| Expanded v2 inventory | **VERIFIED / PARTIALLY_VERIFIED** | Broad v1を壊さず別inventoryを追加。Phase 1は **210**。AutoGluon umbrella 1件をsource-backed **37 implementations**へ展開 | 新規37件すべてruntime-certified、ではない |
| StatsForecast | **VERIFIED / PARTIALLY_VERIFIED** | broad 41、shared明示8。runtime lifecycle / property lifecycle / real-game development evaluationを実装・検証 | broad 41全件の全ゲーム科学評価完了、ではない |
| NeuralForecast fixed | **VERIFIED / PARTIALLY_VERIFIED** | broad 37、shared direct classは17。通常学習経路あり | broad 37全件の全ゲームruntime/OOF完了、ではない |
| NeuralForecast AutoModels | **VERIFIED / PARTIALLY_VERIFIED** | official AutoModel 36、Optuna/Ray、search policy、search-space persistence、seed/precision伝播、GPU evidence pathあり | 36×全ゲームの正式runtime/accuracy certification完了、ではない |
| AutoGluon TimeSeries | **PARTIALLY_VERIFIED** | isolated provider + source inventory。v1.5.0 source manifestは29 models + 8 unique ensemble classes = 37 implementations | Expanded 37件すべてのruntime証明、ではない |
| TSFM runtime audit | **PARTIALLY_VERIFIED** | audit identity 21中 **19 CERTIFIED / 2 BLOCKED** | 19すべてshared-routable、lottery-compatible、OOF優位、ではない |
| Probabilistic platform | **VERIFIED / PARTIALLY_VERIFIED** | separate 72-model catalog、backend probe、compatibility/run/API surfaceあり | 72モデル全ゲームruntime/科学評価完了、ではない |
| Resource-aware campaign | **VERIFIED** | live resource planning、GPU割当、resume fingerprint、timeout process-tree cleanup、outer-worker cap | Broad/Unified全unit完走、ではない |
| GitHub observability | **VERIFIED** | Operations Dashboard / visual dashboard / Pages gate / structured intake実装済み | 各scientific gateの代替、ではない |
| Holdout | **BLOCKED (CLOSED BY POLICY)** | development evidenceが揃うまで閉鎖 | development結果から自動解禁、ではない |
| Prospective | **BLOCKED (CLOSED BY POLICY)** | prediction seal + future actual到着後のみ評価 | Holdout未承認のまま実行可、ではない |
| Automatic promotion | **BLOCKED / FORBIDDEN** | promotionはhuman approval前提 | runtime PASSだけでchampion昇格、ではない |

### 状態語

- **VERIFIED**: current code/history/tests/evidenceで対象の主張を確認済み。
- **PARTIALLY_VERIFIED**: 一部モデル・一部lane・一部実行面のみ実測済み。
- **EXECUTION_PENDING**: 実装・計画はあるが、対象分母の実行完了証拠が未完。
- **BLOCKED**: 明示的なgate、runner、license、artifact、policy等で進行不可。

---

## 2. 何を数えているか — 3つのinventoryを混同しない

| Inventory | 分母 | 目的 | 重要な境界 |
|---|---:|---|---|
| **Broad v1** | **174** | 既存の広い比較在庫。`src/loto/models/catalog_full.py` | 既存 174×6 campaignの分母を途中で変更しないため凍結 |
| **Unified v1** | **250** | model/library/provider/reconciliation等を共通coverageで扱う既存計画 | 全250がstandalone forecasterとは限らない |
| **Expanded v2 Phase 1** | **210** | umbrella entryをsource-backed implementation identityへ分解 | Broad v1を置換しない。新identityはruntime証明を別途要求 |

Expanded v2 Phase 1では Broad v1 の `autogluon-timeseries` 1件を、AutoGluon 1.5.0 source manifestの **29 model aliases + 8 unique ensemble classes = 37 implementations**へ置換するため、`174 - 1 + 37 = 210` です。`ImplementationIdentity.runtime_status` の初期値は `NOT_RUN`、`runtime_certified=False` です。

---

## 3. 6ゲームの共通契約

| game | family | positions | values | semantics |
|---|---|---:|---|---|
| `mini` | select | 5 | 1..31 | 昇順・重複なし |
| `loto6` | select | 6 | 1..43 | 昇順・重複なし |
| `loto7` | select | 7 | 1..37 | 昇順・重複なし |
| `bingo5` | select | 8 | 1..40 | 昇順・重複なし |
| `numbers3` | digits | 3 | 0..9 | 順序あり・重複可 |
| `numbers4` | digits | 4 | 0..9 | 順序あり・重複可 |

`available=true`、import成功、単一ゲームsmokeだけでは「6ゲーム対応」と判定しません。出力shapeは必ずgame geometryへ適合させます。

---

## 4. ライブラリ / framework 対応表

| Library / family | 在庫・代表モデル | 実行面 | 主要機能 / 引数 | 現在状態 |
|---|---|---|---|---|
| builtin | `uniform`, `frequency` 等 | shared | mandatory controls / theory reference | **VERIFIED** |
| scikit-learn | logistic, ridge/elasticnet position, RF, ExtraTrees, HGB | shared | seed、candidate/position feature contract | **VERIFIED / PARTIALLY_VERIFIED** |
| LightGBM | classifier / position | shared | candidate / position boosting | **PARTIALLY_VERIFIED** |
| XGBoost | classifier | shared | candidate boosting | **PARTIALLY_VERIFIED** |
| CatBoost | classifier | shared | candidate boosting | **PARTIALLY_VERIFIED** |
| **StatsForecast** | broad **41** / shared 8 | shared + campaign | statistical forecast、lifecycle、real-game dev evaluation | **VERIFIED / PARTIALLY_VERIFIED** |
| **MLForecast** | Auto inventory **8** / direct shared 2 | shared + research inventory | lag ML、regressor backend | **PARTIALLY_VERIFIED** |
| **NeuralForecast fixed** | broad **37** / direct shared 17 | shared | GPU/CPU deep forecast、exogenous/probabilistic supportはmodel依存 | **PARTIALLY_VERIFIED** |
| **NeuralForecast Auto** | official **36** | dedicated AutoModel runner | `backend`, `config`, `search_alg`, `num_samples`, CPU/GPU, seed, precision, refit | **VERIFIED / PARTIALLY_VERIFIED** |
| **AutoGluon TimeSeries 1.5.0** | broad umbrella 1 / Expanded implementations **37** | isolated provider | model/ensemble inventory、subprocess isolation | **PARTIALLY_VERIFIED** |
| Darts | `RegressionEnsembleModel` lane | shared / optional | NaiveDrift + ExponentialSmoothing ensemble | **PARTIALLY_VERIFIED** |
| GluonTS | Torch DeepAR lane | shared / optional | Student-T probabilistic DeepAR | **PARTIALLY_VERIFIED**; shared path CPU-pinned |
| ReservoirPy | ESN (`Reservoir >> Ridge`) | shared / optional | position-wise reservoir forecasting | **PARTIALLY_VERIFIED** |
| HierarchicalForecast | **10** reconciliation methods | reconciliation | BottomUp / TopDown / MiddleOut / MinTrace / OptimalCombination / ERM等 | **VERIFIED / PARTIALLY_VERIFIED** |
| sktime | campaign identity | isolated campaign | rolling-origin / lifecycle evaluation | **EXECUTION_PENDING** for broad real runtime |
| skforecast | inventory/dependency identity | no audited shared worker | future expanded routing target | **EXECUTION_PENDING** |
| BasicTS | outside Broad 174 | isolated campaign | provider/config/dataset/runtime smoke contracts | **PARTIALLY_VERIFIED** |
| Time-Series-Library | outside Broad 174 | isolated campaign | DLinear/TSMixer/LightTS/SegRNN/FreTS/SCINet/TimeFilter/TiDE/FiLM lane | **PARTIALLY_VERIFIED** |
| Merlion | outside Broad 174 | isolated campaign | ARIMA/ETS/MSES runtime certification surface | **EXECUTION_PENDING** for target-host completion |
| TSFM / foundation models | audit identity **21** | shared provider subset + isolated lanes | pinned revision、load/inference/device/VRAM/shape/finite checks | **19 CERTIFIED / 2 BLOCKED**, routing scopeは別 |
| probabilistic programming | separate **72** | `loto3 probabilistic` | backend probe、compatibility、plan/run/compare/API | **PARTIALLY_VERIFIED** |

---

## 5. NeuralForecast — fixed 37 と AutoModels 36

### 5.1 fixed model inventory 37

```text
RNN GRU LSTM TCN DeepAR DilatedRNN MLP NHITS NBEATS NBEATSx
DLinear NLinear TFT VanillaTransformer Informer Autoformer PatchTST
FEDformer StemGNN HINT TimesNet TimeLLM TSMixer TSMixerx
MLPMultivariate iTransformer BiTCN TiDE DeepNPTS SOFTS SOFTSSharp
TimeMixer KAN RMoK TimeXer xLSTM XLinear
```

通常shared routeのdirect class subsetは次の17です。

```text
DLinear NLinear NHITS NBEATS NBEATSx TiDE TCN GRU LSTM DeepAR
TFT PatchTST TimesNet TSMixer TimeMixer iTransformer VanillaTransformer
```

**37件が在庫にあること**と**37件全部がnormal shared routeから実行できること**は別です。

### 5.2 official AutoModel inventory 36

```text
AutoRNN AutoLSTM AutoGRU AutoTCN AutoDeepAR AutoDilatedRNN AutoBiTCN
AutoxLSTM AutoMLP AutoNBEATS AutoNBEATSx AutoNHITS AutoDLinear AutoNLinear
AutoTiDE AutoDeepNPTS AutoKAN AutoTFT AutoVanillaTransformer AutoInformer
AutoAutoformer AutoFEDformer AutoPatchTST AutoiTransformer AutoTimeXer
AutoTimesNet AutoStemGNN AutoHINT AutoTSMixer AutoTSMixerx
AutoMLPMultivariate AutoSOFTS AutoSOFTSSharp AutoTimeMixer AutoRMoK AutoXLinear
```

Local extensionsはofficial upstream inventoryと分離します。

| local extension | status |
|---|---|
| AutoTimeLLM | fail-closed local extension |
| AutoSCINet | local extension |
| AutoSegRNN | inactive |
| AutoFreTS | inactive |

### 5.3 AutoModel共通引数 / project control

NeuralForecast upstream AutoModelsの共通契約と、repository側で実装したcontrolの関係です。

| 種別 | 引数 / control | 意味 / projectでの扱い |
|---|---|---|
| forecast | `h` | forecast horizon |
| loss | `loss`, `valid_loss` | train / validation objective |
| search space | `config` | model固有default HPO spaceまたはcustom config |
| backend | `backend` | `ray` / `optuna` |
| search | `search_alg` / project search strategy | auto / random / TPE系、backend整合性をfail-closed検証 |
| budget | `num_samples` | HPO trial数 |
| resource | `cpus`, `gpus` | Ray利用時のtrial resource。repositoryはtrial並列/resource planも管理 |
| reproducibility | `random_seed` / CLI seed | outer experiment seedとして固定。HPO dimensionへ勝手に変換しない |
| precision | project `precision` control | actual training configへ伝播。明示model configを優先 |
| refit | `refit_with_val` | best model refit policy |
| observability | `callbacks`, `verbose` | runtime/training evidenceとartifact保存へ接続 |

2026-08-12までのmerged実装では、official per-model default search spaceを維持したまま固定experiment controlをoverlayし、seed/precisionの伝播、multiseries `n_series`、early stop、GPU training/pre-save/reload evidenceをfail-closedで扱うよう修正済みです。

---

## 6. StatsForecast / MLForecast

### StatsForecast

Broad inventoryは **41**。通常shared IDsは意図的に狭く、次の8です。

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

`Croston` / `TSB` は通常position-seriesと同一視せずcandidate-series semanticsを持ちます。

最近のmerged履歴では、runtime lifecycle certification、property lifecycle certification、real-game development evaluation Phase Cが追加されています。これは**科学評価の実行面が実装・検証された**という意味であり、41モデル×6ゲームの全完走を意味しません。

### MLForecast

Broad AutoML inventory 8:

```text
AutoLightGBM AutoXGBoost AutoCatboost AutoLinearRegression
AutoRidge AutoLasso AutoElasticNet AutoRandomForest
```

現在のdirect shared paths:

```text
mlforecast-ridge
mlforecast-lightgbm
```

8件のAuto inventoryを「8 shared workers」と誤記しないでください。

---

## 7. AutoGluon TimeSeries — umbrellaから37 implementationsへ

Pinned source targetは `autogluon.timeseries==1.5.0`。

### 29 source model aliases

```text
ADIDA ARIMA AutoARIMA AutoCES AutoETS Average Croston DLinear DeepAR
DirectTabular DynamicOptimizedTheta ETS IMAPA Chronos Chronos2 NPTS Naive
PatchTST PerStepTabular RecursiveTabular SeasonalAverage SeasonalNaive
SimpleFeedForward TemporalFusionTransformer Theta TiDE Toto WaveNet Zero
```

### 8 unique ensemble classes

```text
Greedy PerItemGreedy PerformanceWeighted SimpleAverage Median Tabular
PerQuantileTabular LinearStacker
```

`Weighted` は `GreedyEnsemble` aliasなのでunique classの分母へ重複加算しません。

Expanded v2はsource-backed identityを作りますが、新identityのdefaultは `runtime_status=NOT_RUN`, `runtime_certified=False` です。source declarationとruntime certificationを分離しています。

---

## 8. TSFM / foundation model runtime reality

Current retained runtime auditは21 identitiesを判定し、**19 CERTIFIED / 2 BLOCKED / 0 pending**です。これはruntime evidenceであってaccuracy/OOF evidenceではありません。

| audit identity | runtime | shared/provider relationshipの要点 |
|---|---|---|
| chronos-2 | CERTIFIED | shared exact ID / ChronosProvider |
| chronos-bolt-tiny | CERTIFIED | shared exact ID / ChronosProvider |
| chronos-t5-small | CERTIFIED | shared exact ID / ChronosProvider |
| chronos-t5-base | CERTIFIED | exact shared ModelSpecなし |
| granite-flowstate-r1 | CERTIFIED | exact shared ModelSpecなし |
| granite-patchtsmixer | CERTIFIED | exact shared ModelSpecなし |
| granite-patchtst | CERTIFIED | exact shared ModelSpecなし |
| granite-ttm-r2 | CERTIFIED | shared `granite-ttm`とはidentity差あり |
| kronos-base | CERTIFIED | native financial OHLCV contract、lottery compatibility=false |
| lag-llama | CERTIFIED | exact shared ModelSpecなし |
| moirai-1.0-base | **BLOCKED** | model weights missing / personal-noncommercial scope |
| moirai-2.0-small | CERTIFIED | shared `moirai`とidentity差あり、lottery compatibility=false |
| moment-1-large | CERTIFIED | forecast head scope要確認 |
| moment-1-small | CERTIFIED | forecast head scope要確認 |
| sundial-base | CERTIFIED | shared `sundial`とidentity差あり |
| t0-alpha | **BLOCKED** | gated access required |
| tabpfn-ts | CERTIFIED | shared exact ID、candidate/foundation-tabular path |
| timesfm-2.5-transformers | CERTIFIED | shared `timesfm-2.5`とidentity/package差あり |
| tirex-2 | CERTIFIED | shared `tirex`とlogical ID差あり |
| toto-2.0-4m | CERTIFIED | exact shared registry entryなし |
| toto-open-base | CERTIFIED | exact shared registry entryなし |

Shared provider registryは21件より狭く、Chronos family / Sundial / TimesFM / Granite TTM / TiRex / Moirai / TabPFN-TSを中心に持ちます。provider不明はfail-closedです。

### Toto 2.0 22M current boundary

PR #296で `Datadog/Toto-2.0-22m` pinned snapshot、CUDA load/inference/replay、seed/precision/evidence infrastructureがmergeされました。ただし正式native-Linux gateは未完です。

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
Holdout=CLOSED
Prospective=CLOSED
automatic promotion=FORBIDDEN
```

したがって「22M runtime certified / shared selectable」とは記載しません。

---

## 9. その他のframework lane

| framework | 実装されている主なもの | 現在の注意点 |
|---|---|---|
| Darts | RegressionEnsembleModel over NaiveDrift + ExponentialSmoothing | framework全model自動展開ではない |
| GluonTS | Torch DeepAR + Student-T | current shared trainerはCPU-pinned。CUDA-certifiedとしない |
| ReservoirPy | Reservoir + Ridge ESN | position-wise lane |
| HierarchicalForecast | BottomUp/TopDown/MiddleOut/MinTrace/OptimalCombination/ERM等10 | reconciliationはstandalone forecasterではない |
| Time-Series-Library | DLinear/TSMixer/LightTS/SegRNN/FreTS/SCINet/TimeFilter/TiDE/FiLM | isolated campaign。upstream全architecture certificationではない |
| BasicTS | provider/config/dataset/runtime smoke contracts | isolated provider surface |
| sktime | rolling-origin campaign/lifecycle machinery | target runtime campaign pending |
| Merlion | ARIMA/ETS/MSES provider/certification path | target-host completion pending |

---

## 10. 全体機能マップ

| 機能 | 実装面 | status / notes |
|---|---|---|
| Canonical game geometry | `loto3 games`, game contracts | **VERIFIED** |
| Data acquisition / raw preservation | `loto data acquire` / acquisition modules | **VERIFIED / PARTIALLY_VERIFIED** per source |
| Broad catalog | `loto3 catalog`, `catalog_full.py` | **VERIFIED**, 174 frozen |
| Shared catalog | `loto models list`, `catalog.py` | **VERIFIED**, broadより狭い |
| Expanded implementation identities | `implementation_catalog.py` | **VERIFIED**, Phase1=210 |
| Model×game planning | `loto3 campaign --plan-only` | **VERIFIED** |
| Resource-aware scheduling | live resource plan / GPU lease / process cleanup | **VERIFIED** via #270/#277 |
| NeuralForecast HPO | `loto neuralforecast automodel-run` | **VERIFIED / PARTIALLY_VERIFIED** |
| StatsForecast lifecycle | dedicated runtime/property/dev evaluation | **VERIFIED / PARTIALLY_VERIFIED** |
| Runtime certification | exact identity/load/inference/device/VRAM/shape/finite checks | framework/model scope dependent |
| Search-space persistence | DB-backed NF artifacts | **VERIFIED** |
| Experiment/run registry | registry APIs / run evidence | **VERIFIED / PARTIALLY_VERIFIED** |
| MLflow-compatible experiment tracking | params/metrics/artifacts integration surfaces | **PARTIALLY_VERIFIED** by execution lane |
| Prediction sealing | sealing/prediction lock modules | **VERIFIED as capability**; prospective use remains gated |
| Hit@±1-first evaluation | evaluation modules | **VERIFIED as metric/protocol capability** |
| MAE/MSE/RMSE | evaluation modules | **VERIFIED** |
| Mandatory baselines | random/fixed/mean/median/recent/frequency/statistical lanes | campaign/protocol dependent |
| OOF | chronological development evaluation surfaces | **PARTIALLY_VERIFIED**; all-model campaign incomplete |
| Holdout | policy gate | **CLOSED** |
| Prospective | sealed future evaluation gate | **CLOSED** |
| Promotion governance | approval/promotion subjects/status taxonomy | **VERIFIED as governance foundation**, auto-promotion forbidden |
| GitHub Operations Dashboard | Actions/Projects/observability docs | **VERIFIED** |
| Visual dashboard / Pages build gate | generated dashboard artifacts | **VERIFIED** |
| Windows portability | Windows CI / portability work | **BLOCKED** by known NTFS-invalid path issue in current program state |

---

## 11. 科学評価の正しい順序

```text
immutable raw data
  -> data/geometry/leakage validation
  -> time-ordered Train / Validation / Holdout / Prospective
  -> Train-only fit of scaler/encoder/feature selection/HPO
  -> chronological OOF with all configured seeds
  -> mandatory baselines
  -> Hit@±1 first + MAE/MSE/RMSE + position metrics
  -> prediction hash/seal before actual is known
  -> runtime/license eligibility
  -> explicit Holdout authorization
  -> explicit Prospective authorization
  -> human promotion approval
```

最良seedだけを抜き出して採用せず、複数seedの平均・分散・worst caseを保存します。

---

## 12. 直近の実装履歴 — fact-checkした主なmerged changes

| PR | merged change | README上の解釈 |
|---:|---|---|
| #252 | geometry-general metrics / hard-code gate | 6-game geometryへ評価を一般化 |
| #253 | theory-aware Hit@±1 promotion foundation | 理論基準をpromotion evidenceへ接続 |
| #254 | MDE / power planning | 科学評価前の検出力設計 |
| #255 | README/docs capability rewrite | 旧文書の大幅整備 |
| #257 | StatsForecast runtime lifecycle certification | lifecycle実行面を実装 |
| #258 | StatsForecast property lifecycle certification | property evidence追加 |
| #259 | StatsForecast real-game development evaluation Phase C | 実ゲームdevelopment lane追加 |
| #260 | NeuralForecast parameter propagation + training evidence | seed/precision/search-space/GPU evidence修正 |
| #261 | NeuralForecast parameter-effect audit planning | OFAT型effect audit計画を実装 |
| #268 | statistical + causal analysis foundation | Holdout/Prospectiveを使わない分析基盤 |
| #270 | runtime audit serialization + resource-aware broad runner | broad campaign execution control強化 |
| #273 | repository observability + structured work intake | GitHub上の状態可視化 |
| #274 | evidence-aware visual dashboard + Pages gate | 証拠ベースdashboard |
| #276 | GitHub operations control center | 最初に見るOperations Dashboard |
| #277 | resource-aware scheduler stabilization | GPU lease/resume/cleanup/worker cap安定化 |
| #293 | Expanded v2 inventory + AutoGluon expansion | Broad v1凍結のまま210へ展開 |
| #295 | Toto2 family manifest / provenance gate | source identityとprovenanceをfail-closed化 |
| #298 | unintended Toto 22M probe revert | 意図しないprobeをmainから除去 |
| #296 | Toto2 22M pinned CUDA replay infrastructure | native-Linux formal certification前の部分証拠。shared routing未解禁 |

**履歴にPRがあること自体を実装済み証拠にはしません。** current `main` にコードが残っているか、merge済みか、必要なtests/evidenceがあるかを合わせて判定します。

---

## 13. まだ完了していない主要作業

1. Broad v1 **174 × 6 = 1044** unitのruntime-remediation込み完走。
2. Unified v1 **250 × 6 = 1500** unitのcoverage実行・結果集約。
3. Expanded v2のAutoGluon以外（Darts / GluonTS / sktime/skforecast / Time-Series-Library / BasicTS等）のsource-backed展開とruntime campaign。
4. NeuralForecast AutoModels 36を同一条件で全ゲームruntime認証し、GPU/CPU fallbackを明示。
5. development OOFをHit@±1最優先で完了し、Random/固定値/平均/中央値/直近値/頻度/統計baselineと比較。
6. Toto 2.0 22Mのnative-Linux external GPU PID/VRAM/release gateを完了するまで `runtime_certified=false` を維持。
7. Windows portability blockerの解消。
8. Holdout / Prospectiveはdevelopment evidenceと明示承認が揃うまで閉じたまま維持。

---

## 14. よく使う入口

```bash
# 6ゲームgeometry
uv run loto3 games

# Broad 174 inventory
uv run loto3 catalog --counts

# Shared executable surface
uv run loto models list

# model×game plan only
uv run loto3 campaign --output unused --plan-only

# NeuralForecast AutoModels
uv run loto neuralforecast automodel-run --help

# Probabilistic catalog/backend
uv run loto3 probabilistic catalog-list
uv run loto3 probabilistic backends

# TSFM pinned revisions
uv run loto3 revisions --help

# Data acquisition
uv run loto data acquire --help
```

---

## 15. 正本 / 詳細資料

実装状態の判定はMarkdown単独ではなく、次の順に確認してください。

1. **current code**
   - `src/loto/models/catalog_full.py`
   - `src/loto/models/catalog.py`
   - `src/loto/models/implementation_catalog.py`
   - `src/loto/models/providers.py`
   - framework-specific `*_campaign` / `neuralforecast` / `statsforecast` modules
2. **tests / workflows / retained artifacts**
3. **merged PR / commit history**
4. **live project state**
5. documentation

詳細資料:

- [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md)
- [`docs/TSFM_RUNTIME_CAPABILITIES.md`](docs/TSFM_RUNTIME_CAPABILITIES.md)
- [`docs/operations/`](docs/operations/)
- [`docs/observability_expansion/`](docs/observability_expansion/)
- [`docs/evaluation/`](docs/evaluation/)

Upstream references:

- NeuralForecast: https://nixtlaverse.nixtla.io/neuralforecast/
- StatsForecast: https://nixtlaverse.nixtla.io/statsforecast/
- MLForecast: https://nixtlaverse.nixtla.io/mlforecast/
- HierarchicalForecast: https://nixtlaverse.nixtla.io/hierarchicalforecast/
- Ray Tune: https://docs.ray.io/en/latest/tune/
- Optuna: https://optuna.readthedocs.io/
- MLflow: https://mlflow.org/docs/latest/

---

## 16. 読み方の原則

このrepositoryでは次を常に分けます。

```text
source-declared
catalog-registered
shared-routable
provider-routable
load-verified
inference-verified
runtime-certified
lottery-compatible
OOF-evaluated
Holdout-evaluated
Prospective-evaluated
promotion-eligible
```

上の段階を飛ばして、下の段階をREADMEやdashboardで主張しないことが基本ルールです。
