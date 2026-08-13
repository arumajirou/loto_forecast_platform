# Loto Forecast Platform

**ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4**を対象に、統計モデル、機械学習、深層学習、AutoML、時系列基盤モデル（TSFM）、確率モデルを、時系列リークを防いだ共通契約で比較・検証・運用する研究プラットフォームです。

このREADMEは「何が使えるか」「どこまで実証済みか」「次に何を検証すべきか」を最短で把握する入口です。モデル・ライブラリ別の詳細は専用対応表へ分離しています。

> **Implementation audit base:** `main@ed7d6c8151254653d44296b608457200ac80c5ce` (2026-08-13)  
> **Latest merged boundary:** PR #307 — sktime P1 input-contract normalization fix  
> **Rule:** `REGISTERED != ROUTABLE != RUNTIME_CERTIFIED != OOF_EVALUATED != HOLDOUT_EVALUATED != PROSPECTIVE_EVALUATED != PROMOTION_ELIGIBLE`  
> 現在のpackage versionはREADMEへ手書きしません。canonical versionは`loto.version.__version__` / installed package metadata / `loto-build-info`を正本とします。

## まず見る資料

| 知りたいこと | 資料 |
|---|---|
| ライブラリごとのモデル一覧・引数・対応機能・実装状況 | **[`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md)** |
| 実行コマンド・機能の詳細 | [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md) |
| scikit-learn dynamic all-estimator provider | [`docs/SKLEARN_ALL_MODELS.md`](docs/SKLEARN_ALL_MODELS.md) |
| 6ゲーム並列Unified Campaign / live progress | [`docs/PARALLEL_UNIFIED_CAMPAIGN.md`](docs/PARALLEL_UNIFIED_CAMPAIGN.md) |
| LightGBM GPU build / backend認証 | [`docs/LIGHTGBM_GPU_CERTIFICATION.md`](docs/LIGHTGBM_GPU_CERTIFICATION.md) |
| sktime P1 certification runner | [`scripts/run_sktime_p1_matrix_certification.sh`](scripts/run_sktime_p1_matrix_certification.sh) |
| TSFM 21 identityのruntime証拠 | [`docs/TSFM_RUNTIME_CAPABILITIES.md`](docs/TSFM_RUNTIME_CAPABILITIES.md) |
| 評価・Hit@±1・OOF関連 | [`docs/evaluation/`](docs/evaluation/) |
| 運用・監視 | [`docs/operations/`](docs/operations/) |

---

## 1. 現在地

| 領域 | 状態 | 現在確認できること | まだ意味しないこと |
|---|---|---|---|
| 6ゲーム geometry | **VERIFIED** | 6ゲームのpositions・値域・select/digits契約あり | 全モデル×全ゲーム完走ではない |
| Broad v1 | **VERIFIED** | frozen inventory **174** | 174全件runtime成功ではない |
| Unified v1 | **EXECUTION_PENDING** | **250 × 6 = 1500 units** の計画分母 | 1500完走ではない |
| Parallel Unified Campaign | **VERIFIED / PARTIALLY_VERIFIED** | game単位process並列、CPU affinity/thread制限、`progress.json`、live status、集約artifactを実装 | 全174×6 real-data完走ではない |
| Expanded v2 Phase 1 | **VERIFIED / PARTIALLY_VERIFIED** | **210 identities**。AutoGluon umbrellaを37実装へ展開 | 210全件runtime-certifiedではない |
| scikit-learn Broad | **VERIFIED / PARTIALLY_VERIFIED** | Broad 7。`isotonic-calibrated-logistic`のfactory/routing gapを解消 | post-fix real-data 42/42成功をまだ主張しない |
| scikit-learn dynamic provider | **VERIFIED / PARTIALLY_VERIFIED** | `loto-sklearn`、installed-version dynamic inventory、smoke/certify surfaceを実装 | installed versionごとの全 estimator が常に成功する意味ではない |
| StatsForecast | **VERIFIED / PARTIALLY_VERIFIED** | Broad 41 / shared explicit 8 / lifecycle + real-game dev lane | 41×6完走ではない |
| NeuralForecast fixed | **VERIFIED / PARTIALLY_VERIFIED** | Broad 37 / direct shared subset 17 | 37全件runtime/OOF完了ではない |
| NeuralForecast Auto | **VERIFIED / PARTIALLY_VERIFIED** | official 36 / Ray・Optuna / seed・precision・GPU evidence path | 36×6正式認証完了ではない |
| MLForecast | **PARTIALLY_VERIFIED** | Auto inventory 8 / direct shared 2 | Auto 8 = shared workers 8ではない |
| AutoGluon TimeSeries | **PARTIALLY_VERIFIED** | source 29 models + 8 unique ensembles = 37 expanded identities | 37全件runtime-certifiedではない |
| Tree GPU routing | **VERIFIED** | XGBoost / CatBoostはGPU lease runtime確認済み。LightGBM classifier/positionはcertified OpenCL GPU backendへrouting | 全tree modelの全ゲームOOF優位ではない |
| LightGBM CUDA | **NOT CERTIFIED / FAIL-CLOSED** | resolved buildではOpenCL `device_type="gpu"`を使用 | `device_type="cuda"`対応を意味しない |
| sktime | **PARTIALLY_VERIFIED / MERGED #307** | sktime 1.0.1 laneでregistry **141 discovered / 141 importable / 53 core / 88 optional**。P1固定4モデルはfit/predict/save-load/formal verification PASS | 141全件runtime-certified、6ゲームOOF完走、accuracy優位ではない |
| TSFM | **PARTIALLY_VERIFIED** | retained audit 21中 **19 CERTIFIED / 2 BLOCKED** | 19全てlottery-compatible/OOF済みではない |
| Probabilistic platform | **VERIFIED / PARTIALLY_VERIFIED** | separate **72-model** catalog + backend/run/API surface | 72全件科学評価完了ではない |
| Holdout | **BLOCKED / CLOSED** | explicit authorization前は閉鎖 | development結果から自動解禁されない |
| Prospective | **BLOCKED / CLOSED** | prediction seal後のfuture evaluationのみ | Holdout未承認で進めない |
| Auto promotion | **FORBIDDEN** | human approval前提 | runtime PASSだけでchampion化しない |

### 状態語

| status | 意味 |
|---|---|
| `VERIFIED` | current code / tests / retained evidenceで主張を確認済み |
| `PARTIALLY_VERIFIED` | 一部モデル・一部lane・一部証拠のみ成立 |
| `EXECUTION_PENDING` | 実装または計画はあるが対象分母の実行完了証拠がない |
| `BLOCKED` | policy / runner / license / artifact等の明示gateで停止 |
| `NOT CERTIFIED` | 実装可否とruntime認証を分離し、成功証拠がない機能をfail-closedで扱う |

> PR上のexact-worktree証拠と、merge後`main`上の正式再認証は別の証拠クラスです。sktime P1はPR #307で修正・認証済みですが、P0〜P4を同一のmerge後main SHAで揃える最終再認証は別途必要です。

---

## 2. Broad v1 = 174 のライブラリ内訳

この数は `src/loto/models/catalog_full.py` の current code から構成されます。

| Library | Count | 主な役割 | 詳細 |
|---|---:|---|---|
| builtin | 4 | theory / frequency controls | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#4-builtin--scikit-learn--boosting) |
| scikit-learn | 7 | candidate / position ML | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#4-builtin--scikit-learn--boosting) |
| LightGBM | 2 | candidate / position boosting | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#4-builtin--scikit-learn--boosting) |
| XGBoost | 1 | candidate boosting | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#4-builtin--scikit-learn--boosting) |
| CatBoost | 1 | candidate boosting | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#4-builtin--scikit-learn--boosting) |
| StatsForecast | **41** | statistical forecasting | [41モデル一覧](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#5-statsforecast--41-models) |
| NeuralForecast fixed | **37** | deep forecasting | [37モデル一覧](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#7-neuralforecast-fixed--37-models) |
| NeuralForecast Auto | **36** | AutoModel HPO | [36モデル一覧](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#8-neuralforecast-automodels--official-36) |
| MLForecast Auto | **8** | lag AutoML | [8モデル一覧](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#6-mlforecast--auto-8--direct-shared-2) |
| HierarchicalForecast | **10** | reconciliation | [10 method一覧](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#10-hierarchicalforecast--10-reconciliation-methods) |
| TSFM | **21** | foundation / zero-shot | [21 runtime identities](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#11-tsfm--foundation-models--21-runtime-audit-identities) |
| AutoGluon | 1 umbrella | AutoML / ensemble | [Expanded 37 identities](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#9-autogluon-timeseries-150--expanded-v2-phase-1) |
| Darts | 1 | ensemble framework | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#12-darts--gluonts--reservoirpy--sktime--skforecast) |
| GluonTS | 1 | probabilistic DeepAR | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#12-darts--gluonts--reservoirpy--sktime--skforecast) |
| ReservoirPy | 1 | ESN | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#12-darts--gluonts--reservoirpy--sktime--skforecast) |
| sktime | 1 | forecasting framework umbrella | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#12-darts--gluonts--reservoirpy--sktime--skforecast) |
| skforecast | 1 | recursive lag ML | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#12-darts--gluonts--reservoirpy--sktime--skforecast) |
| **TOTAL** | **174** |  | frozen denominator |

Broad v1の174は**凍結された科学比較分母**です。次のdynamic/expanded inventoryを174へ足し戻しません。

- scikit-learn `loto-sklearn`: installed versionから`sklearn.utils.all_estimators()`で動的発見
- sktime isolated campaign: `sktime.registry.all_estimators(estimator_types="forecaster")`で動的発見
- Expanded v2 identities
- Time-Series-Library / BasicTS / Merlion
- separate probabilistic 72-model catalog

したがって、`Broad 174`、`scikit-learn dynamic denominator`、`sktime registry 141`は別の分母です。

---

## 3. 主要ライブラリの対応関係

| Library | Inventory | Shared route | Provider / isolated | HPO | GPU | runtime evidence | 全ゲームOOF |
|---|---:|---|---|:---:|:---:|---|---|
| scikit-learn Broad | 7 | candidate / position | Unified Campaign | — | CPU + tree-specific routing | **部分検証** | **未完** |
| scikit-learn dynamic | version-dependent | — | `loto-sklearn` | — | estimator依存 | provider/certification surface **VERIFIED** | **未完** |
| XGBoost | Broad 1 | candidate | resource-aware Unified Campaign | — | **CUDA GPU VERIFIED** | exact-head GPU runtime **VERIFIED** | **未完** |
| CatBoost | Broad 1 | candidate | resource-aware Unified Campaign | — | **GPU VERIFIED** | exact-head GPU runtime **VERIFIED** | **未完** |
| LightGBM | Broad 2 | candidate / position | resource-aware Unified Campaign | — | **OpenCL GPU VERIFIED** / CUDA build未認証 | classifier + position runtime **VERIFIED** | **未完** |
| StatsForecast | 41 | 8 explicit | campaign | model内Auto | CPU中心 | **部分検証** | **未完** |
| MLForecast | Auto 8 | 2 direct | AutoML/research | ✓ | backend依存 | **部分検証** | **未完** |
| NeuralForecast fixed | 37 | 17 direct | dedicated paths | — | ✓ | **部分検証** | **未完** |
| NeuralForecast Auto | 36 | AutoModel specs | dedicated runner | **Ray / Optuna** | ✓ | **部分検証** | **未完** |
| AutoGluon | umbrella 1 / expanded 37 | umbrella | isolated provider | AutoML | backend依存 | **部分検証** | **未完** |
| HierarchicalForecast | 10 | reconciliation | optional | — | — | capability verified | base forecast依存 |
| TSFM | 21 audit ids | subset | provider-specific | — | 多くで対象 | **19 CERTIFIED / 2 BLOCKED** | **未完** |
| Darts | 1 Broad | ✓ optional | optional | — | optional | **部分検証** | **未完** |
| GluonTS | 1 Broad | ✓ optional | optional | — | shared path CPU-pinned | **部分検証** | **未完** |
| ReservoirPy | 1 Broad | ✓ optional | optional | — | CPU中心 | **部分検証** | **未完** |
| sktime | Broad umbrella 1 / registry 141 | — | isolated campaign | framework依存 | P1 CPU | dynamic inventory + fixed 4-model P1 **VERIFIED on PR #307 worktree** | **未完** |
| skforecast | 1 Broad | — | pending | — | regressor依存 | **EXECUTION_PENDING** | **未完** |

モデル名、class、主要引数、capabilityの詳細は **[`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md)** を参照してください。

### 3.1 2026-08-13 最新実装・認証差分

| PR / main SHA | 状態 | 追加・修正した実体 | 証拠境界 |
|---|---|---|---|
| #301 / `3cc73dba...` | **MERGED** | dynamic all-estimator scikit-learn provider、`loto-sklearn` CLI | provider実装とversion-dependent certification surface。別環境の全件成功を一般化しない |
| #302 / `7d75dadc...` | **MERGED** | 6ゲームprocess並列Unified Campaign、CPU affinity/thread制限、live progress、aggregate artifacts | scheduling/runtime orchestration。scientific split/lock semanticsは既存campaignを使用 |
| #303 / `b9be4174...` | **MERGED** | `isotonic-calibrated-logistic`を`CalibratedClassifierCV`としてfactory/routingへ接続 | synthetic route + prediction lock確認。post-fix real-data 42/42は別途再実行が必要 |
| #304 / `de1444af...` | **MERGED** | GPU leaseをXGBoost/CatBoost constructorへ接続 | RTX 5070 Ti exact-head runtime + external GPU telemetryでVERIFIED |
| #305 / `a03053ea...` | **MERGED** | fail-closed LightGBM GPU build/backend probe | resolved buildはCUDA tree learner非対応、OpenCL `device_type="gpu"`はruntime VERIFIED |
| #306 / `feb4ea5e...` | **MERGED** | LightGBM classifier/positionをcertified OpenCL GPU laneへrouting | GPU lease、device id、runtime、telemetry VERIFIED。CUDA supportは主張しない |
| #307 / `ed7d6c81...` | **MERGED / CURRENT AUDIT BASE / P1 LOCAL VERIFIED** | sktime formal P1 series hashをproviderの`list[float]`正規化境界へ一致 | focused tests PASS、P1 4/4 PASS、formal report PASS、SHA-256 PASS。P0〜P4のmerge後main同一SHA再認証は別gate |

#### sktime P1で現在実証できている範囲

```text
sktime = 1.0.1
registry discovered = 141
registry importable = 141
core compatible = 53
optional dependency declared = 88

formal P1 models = 4
- NaiveForecaster(last)
- PolynomialTrendForecaster(degree=1)
- ExponentialSmoothing
- ThetaForecaster

4/4:
  dependency PASS
  import PASS
  construct PASS
  fit PASS
  predict PASS
  finite output PASS
  save/load PASS
  exact re-prediction match PASS

formal verifier = PASS
input-contract numeric normalization = PASS
artifact SHA-256 verification = PASS
```

このP1証拠は**141 forecasterのruntime認証ではありません**。dynamic inventoryは発見/importabilityの分母であり、optional dependency family、全constructor、全fit/predict、全ゲームOOFはExpanded v2の別実行対象です。

---

## 4. 6ゲーム共通契約

| game | family | positions | values | semantics |
|---|---|---:|---|---|
| `mini` | select | 5 | 1..31 | 昇順・重複なし |
| `loto6` | select | 6 | 1..43 | 昇順・重複なし |
| `loto7` | select | 7 | 1..37 | 昇順・重複なし |
| `bingo5` | select | 8 | 1..40 | 昇順・重複なし |
| `numbers3` | digits | 3 | 0..9 | 順序あり・重複可 |
| `numbers4` | digits | 4 | 0..9 | 順序あり・重複可 |

`available=true`、import成功、単一ゲームsmokeだけでは「6ゲーム対応」と判定しません。

---

## 5. 実装済みと科学的成功を分ける

確認順序は次です。

```text
source-declared
  -> catalog-registered
  -> shared/provider-routable
  -> dependency/version verified
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
```

上の段階を飛ばして、下の段階をREADMEやdashboardで主張しません。

### 科学評価の必須条件

| 項目 | contract |
|---|---|
| primary metric | **Hit@±1** |
| secondary | MAE / MSE / RMSE / position-wise Hit@±1 / all-position Hit@±1 |
| baselines | Random / fixed / mean / median / recent / frequency / statistical |
| split | chronological Train / Validation / Holdout / Prospective |
| preprocessing / HPO | Train内だけでfit |
| seeds | 全設定seed。平均・分散・worstを保存 |
| prediction lock | actual判明前にSHA-256 + timestampで固定 |
| Holdout | explicit authorizationのみ |
| Prospective | sealed future predictionをactual到着後に評価 |
| promotion | human approval。自動promotionは禁止 |

`matrix_complete=true`は「要求したmodel×gameの結果行が揃った」ことを意味し、全行成功や精度優位を意味しません。

---

## 6. TSFMの読み方

Retained auditでは21 identities中 **19 runtime CERTIFIED / 2 BLOCKED** です。

ただし、これは次を意味しません。

- 19件すべてshared routeから選択可能
- 19件すべてlottery-domain compatible
- 19件すべてOOF evaluated
- 19件すべて精度優位

例として Kronos Base はruntime evidenceを持ちますがnative domainはfinancial OHLCVで、lottery compatibilityはfalseです。Moirai 1.0 Baseはweights不足、T0 Alphaはgated accessでBLOCKEDです。

Toto 2.0 22Mも現時点では次を維持します。

```text
runtime_certified=false
shared_routing_allowed=false
OOF=NOT_RUN
Holdout=CLOSED
Prospective=CLOSED
automatic promotion=FORBIDDEN
```

個別21 identityは[TSFM対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#11-tsfm--foundation-models--21-runtime-audit-identities)を参照してください。

---

## 7. よく使うコマンド

```bash
# 6ゲームgeometry
uv run loto3 games

# Broad v1 inventory / counts
uv run loto3 catalog --counts
uv run loto3 catalog

# shared ModelSpec surface
uv run loto models list

# model × game plan only
uv run loto3 campaign --output unused --plan-only

# parallel Unified Campaign help / live progress runner
uv run python -m loto.evaluation.parallel_campaign --help

# dynamic scikit-learn provider
uv run loto-sklearn list
uv run loto-sklearn list --kind regressor
uv run loto-sklearn smoke --model RandomForestRegressor --seed 1
uv run loto-sklearn certify --kind all --seed 1 --output artifacts/sklearn-certification

# sktime P1 formal matrix certification
ROOT="$PWD" SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p1_matrix_certification.sh

# NeuralForecast AutoModels
uv run loto neuralforecast automodel-run --help

# probabilistic platform
uv run loto3 probabilistic catalog-list
uv run loto3 probabilistic backends

# TSFM revisions
uv run loto3 revisions --help

# data acquisition
uv run loto data acquire --help
```

---

## 8. Source of truth

実装状態はMarkdown単独で判定しません。優先順は次です。

1. current code
   - `src/loto/models/catalog_full.py`
   - `src/loto/models/catalog.py`
   - `src/loto/models/implementation_catalog.py`
   - `src/loto/models/providers.py`
   - `src/loto/evaluation/unified_campaign.py`
   - `src/loto/evaluation/parallel_campaign.py`
   - `src/loto/sklearn_provider/`
   - `src/loto/orchestration/resource_scheduler.py`
   - `src/loto/lightgbm_gpu/`
   - `src/loto/sktime_campaign/`
   - framework-specific campaign / provider modules
2. tests / workflows / retained runtime artifacts
3. exact-head local/runtime certification evidence with source SHA and environment provenance
4. merged PR / commit history
5. live Linear project state
6. documentation

PR/worktreeで成功した証拠は、そのsource SHAに対する証拠です。merge後にmainが変わった場合、必要なformal certificationは新しいmain SHAで再実行し、異なるSHAの成功証拠を1つの「同一main VERIFIED」として混ぜません。

詳細資料:

- **[`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md)**
- [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md)
- [`docs/SKLEARN_ALL_MODELS.md`](docs/SKLEARN_ALL_MODELS.md)
- [`docs/PARALLEL_UNIFIED_CAMPAIGN.md`](docs/PARALLEL_UNIFIED_CAMPAIGN.md)
- [`docs/LIGHTGBM_GPU_CERTIFICATION.md`](docs/LIGHTGBM_GPU_CERTIFICATION.md)
- [`docs/TSFM_RUNTIME_CAPABILITIES.md`](docs/TSFM_RUNTIME_CAPABILITIES.md)
- [`docs/evaluation/`](docs/evaluation/)
- [`docs/operations/`](docs/operations/)