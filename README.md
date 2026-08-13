# Loto Forecast Platform

**ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4**を対象に、統計モデル、機械学習、深層学習、AutoML、時系列基盤モデル（TSFM）、確率モデルを、時系列リークを防いだ共通契約で比較・検証・運用する研究プラットフォームです。

このREADMEは「何が実装されているか」「どの分母を見ているか」「どこまでruntime/scientific evidenceがあるか」を最短で把握する入口です。

> **Expanded v2 Phase 3 base:** `main@eb988d2947994bb637dc8f0cbc40afa05570027f` (after PR #316, 2026-08-13)  
> **Critical count rule:** `Broad v1 count != Committed Expanded v2 count != discovered/source count != runtime-certified count`  
> **Scientific rule:** `REGISTERED != ROUTABLE != RUNTIME_CERTIFIED != OOF_EVALUATED != HOLDOUT_EVALUATED != PROSPECTIVE_EVALUATED != PROMOTION_ELIGIBLE`  
> package versionはREADMEへ手書きしません。`loto.version.__version__` / installed metadata / `loto-build-info`を正本とします。

## まず見る資料

| 知りたいこと | 資料 |
|---|---|
| **Broad=1と実モデル/Expanded数の違い** | **[`docs/INVENTORY_COUNT_BOUNDARIES.md`](docs/INVENTORY_COUNT_BOUNDARIES.md)** |
| **GluonTS Expanded v2 Phase 3** | **[`docs/gluonts/GLUONTS_EXPANDED_V2_PHASE3.md`](docs/gluonts/GLUONTS_EXPANDED_V2_PHASE3.md)** |
| ライブラリ別モデル・引数・対応機能 | [`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md) |
| current state / open gates | [`docs/STATUS.md`](docs/STATUS.md) |
| 現在の検証境界 | [`docs/CURRENT_VERIFICATION_REPORT.md`](docs/CURRENT_VERIFICATION_REPORT.md) |
| 次に作業する人向け引継ぎ | [`docs/CURRENT_HANDOFF.md`](docs/CURRENT_HANDOFF.md) |
| 実行・運用機能 | [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md) |
| skforecast 0.23.0 operator evidence | [`docs/SKFORECAST_RUNTIME_CERTIFICATION.md`](docs/SKFORECAST_RUNTIME_CERTIFICATION.md) |
| Darts current state | [`docs/darts/CURRENT_STATE_DARTS.md`](docs/darts/CURRENT_STATE_DARTS.md) |
| dynamic sklearn | [`docs/SKLEARN_ALL_MODELS.md`](docs/SKLEARN_ALL_MODELS.md) |
| parallel Broad campaign | [`docs/PARALLEL_UNIFIED_CAMPAIGN.md`](docs/PARALLEL_UNIFIED_CAMPAIGN.md) |
| LightGBM GPU | [`docs/LIGHTGBM_GPU_CERTIFICATION.md`](docs/LIGHTGBM_GPU_CERTIFICATION.md) |
| TSFM | [`docs/TSFM_RUNTIME_CAPABILITIES.md`](docs/TSFM_RUNTIME_CAPABILITIES.md) |

---

## 1. 現在地

| 領域 | 状態 | 現在確認できること | まだ意味しないこと |
|---|---|---|---|
| 6ゲーム geometry | **VERIFIED** | positions・値域・select/digits契約 | 全モデル×全ゲーム完走ではない |
| Broad v1 | **VERIFIED / FROZEN** | **174 canonical identities** | upstream実モデル総数ではない |
| Probabilistic v1 | **VERIFIED / PARTIALLY_VERIFIED** | effective catalog **76** | Broad plannerへ自動結合されない |
| Combined accounting | **250 identities** | 174 + 76、6ゲーム換算1,500 cells | current単一campaignが1,500行を生成する意味ではない |
| Broad campaign planner | **VERIFIED CONTRACT** | `174 × 6 = 1,044` units | probabilistic 76を含まない |
| Expanded v2 | **PHASE 3 / SOURCE-BACKED** | AutoGluon 37 + GluonTS 9を含むderived total **218** | 218全件runtime-certified、最終inventory freezeではない |
| scikit-learn dynamic | **VERIFIED / PARTIALLY_VERIFIED** | installed-version discovery / smoke / certify | 全estimator成功保証ではない |
| StatsForecast | **VERIFIED / PARTIALLY_VERIFIED** | Broad 41 / shared 8 / development evidence | Holdout/Prospectiveではない |
| NeuralForecast fixed | **VERIFIED / PARTIALLY_VERIFIED** | Broad 37 / shared subset 17 | 37全件OOF完了ではない |
| NeuralForecast Auto | **VERIFIED / PARTIALLY_VERIFIED** | official 36 / Ray / Optuna / GPU evidence path | 36×6 formal完了ではない |
| AutoGluon | **EXPANDED 37 / PARTIAL RUNTIME** | 29 source models + 8 unique ensembles | 37全件runtime-certifiedではない |
| Darts | **BROAD 1 / SOURCE SURFACE >1** | 58 public forecasting exportsをPhase 2で調査、local NLinear/DLinear GPU evidence | 58全件standalone/runtime-certifiedではない |
| GluonTS | **BROAD 1 / EXPANDED 9** | P6 registryの9 estimatorをExpanded identityへ統合。Draft #309 exact-headは2 lanes × 9 = 18/18 CPU lifecycle VERIFIED | 18 unique modelsではない。#309 main統合/GPU/OOFではない |
| sktime | **BROAD 1 / REGISTRY 141** | 141 discovered/importable、53 core-compatible、88 optional、formal P1=4 | 141全件runtime-certifiedではない |
| skforecast | **BROAD 1 / EVIDENCE PLAN 18** | 0.23.0 evidenceから18 candidate implementation identitiesを区別可能 | committed Expanded v2はまだ1。18 runtime-certifiedではない |
| ReservoirPy | **BROAD 1 / EXPANSION OPEN** | current Broad identity + expansion issue #294 | final scientifically distinct count未freeze |
| TSFM | **PARTIALLY_VERIFIED** | retained 21中19 CERTIFIED / 2 BLOCKED | 全19 OOF済みではない |
| Holdout | **CLOSED** | explicit authorizationまで閉鎖 | development結果から自動解禁されない |
| Prospective | **CLOSED** | sealed future predictionのみ | Holdout未承認で自動進行しない |
| Automatic promotion | **FORBIDDEN** | human approval前提 | runtime PASSだけでchampion化しない |

### 状態語

| status | 意味 |
|---|---|
| `VERIFIED` | stated current-code/evidence scopeで確認済み |
| `PARTIALLY_VERIFIED` | 一部identity/lane/environmentのみ成立 |
| `OPERATOR_LOCAL_EVIDENCE` | maintainer-host exact-source evidence、current-main retained certificationとは別 |
| `EXACT_HEAD_VERIFIED` | 特定PR/source SHA上の証拠。merge後mainとは別 |
| `LOCAL_VERIFIED / MAIN_PENDING` | local exact worktreeで成立、main未反映 |
| `EXECUTION_PENDING` | 実装/計画あり、対象分母の完走なし |
| `BLOCKED` | dependency/license/runner/policy/artifactで停止 |
| `NOT CERTIFIED` | 成功証拠なし、fail-closed |

---

## 2. Inventory countをどう読むか

### 2.1 Broad v1 = 174 は凍結分母

次の表は**現在のライブラリ総モデル数ではありません**。既存Broad campaignとの互換性のため凍結したcanonical identity数です。

| Library | Broad v1 count (frozen) |
|---|---:|
| builtin | 4 |
| scikit-learn | 7 |
| LightGBM | 2 |
| XGBoost | 1 |
| CatBoost | 1 |
| StatsForecast | 41 |
| NeuralForecast fixed | 37 |
| NeuralForecast Auto | 36 |
| MLForecast Auto | 8 |
| HierarchicalForecast | 10 |
| TSFM | 21 |
| AutoGluon | 1 umbrella |
| Darts | 1 umbrella |
| GluonTS | 1 canonical identity |
| ReservoirPy | 1 umbrella |
| sktime | 1 umbrella |
| skforecast | 1 Broad identity |
| **TOTAL** | **174** |

### 2.2 umbrellaの「1」と現在確認できる実体数

`1` を見て「1モデルしかない」と判断しません。

| Library | Broad v1 | Committed Expanded v2 after Phase 3 | Observed / discovered / evidence denominator | Current gate |
|---|---:|---:|---|---|
| AutoGluon | 1 | **37** | 29 base + 8 unique ensembles | inventory merged previously |
| Darts | 1 | **1** | **58 public forecasting exports** | #286 / TAJ-27 open |
| GluonTS | 1 | **9** | **9 estimator algorithms**, 2 isolated lanes = **18 lifecycle cells** | #288 inventory integration; #309 runtime repair main pending |
| ReservoirPy | 1 | **1** | final distinct count未freeze | #294 open |
| sktime | 1 | **1** | **141 discovered/importable** | #289 / TAJ-32 open |
| skforecast | 1 | **1** | **18 candidate implementation identities** from current evidence plan | #289 / TAJ-32 open |

### 2.3 current totals

```text
Broad v1                                      = 174
Probabilistic effective v1                    = 76
Combined Broad + Probabilistic accounting     = 250
Current Broad campaign planner                = 174 × 6 = 1,044
Combined accounting × six games               = 250 × 6 = 1,500
Expanded v2 Phase 1 historical                = 210
Expanded v2 after GluonTS Phase 3             = 218
```

Phase 3の218はコードから導出します。

```text
174
- AutoGluon umbrella 1
- GluonTS umbrella 1
+ AutoGluon implementations 37
+ GluonTS implementations 9
= 218
```

Darts / ReservoirPy / sktime / skforecast / Time-Series-Library / BasicTSの今後の分解はまだ218へ入っていないため、**218はExpanded v2の最終freeze値ではありません**。

詳細: [`docs/INVENTORY_COUNT_BOUNDARIES.md`](docs/INVENTORY_COUNT_BOUNDARIES.md)

---

## 3. skforecast — Broad 1 / evidence plan 18 / committed Expanded 1

`docs/SKFORECAST_RUNTIME_CERTIFICATION.md` のcurrent 0.23.0 evidence planから、無意味なwrapper×estimator Cartesian productを避けて次の18 candidate identitiesを区別できます。

| Group | Count | Evidence boundary |
|---|---:|---|
| recursive Ridge | 1 | PASS operator-local |
| recursive HistGradientBoosting | 1 | PASS operator-local |
| recursive LightGBM / XGBoost / CatBoost | 3 | CPU smoke PASS |
| direct Ridge | 1 | PASS |
| recursive multi-series Ridge | 1 | PASS |
| direct multivariate Ridge | 1 | PASS |
| EquivalentDate | 1 | PASS |
| Stats ARAR | 1 | PASS |
| RNN LSTM / GRU | 2 | GPU + CPU fallback evidence |
| Foundation Chronos-2 / TimesFM 2.5 / Moirai-2 / TabICL v2 / TabPFN-TS / T0 | 6 | mixed PASS/BLOCKED/PENDING |
| **Total candidate identities** | **18** | **not a committed Expanded count** |

Important boundaries:

- Chronos-2: GPU/CPU + exog/interval operator evidence.
- TimesFM 2.5: GPU/CPU + interval/quantiles operator evidence.
- TabICL v2: GPU/CPU + exog/interval/quantiles + checkpoint SHA-256 evidence.
- Moirai-2: unsupported dependency metadata override下ではruntime PASS、normal dependency routabilityはBLOCKED。
- TabPFN-TS v3: adapter setupは到達したがauthentication/license gateでcheckpoint取得前に停止、inference NOT_EXECUTED。
- T0: current skforecast-specific sequenceでは未実行。

`src/loto/models/implementation_catalog.py` がまだskforecast umbrellaを18へ分解していないため、**committed Expanded v2 countは1のまま**です。これは#289 / TAJ-32で解消すべき実装gapです。

---

## 4. GluonTS — Broad 1 / Expanded 9 / lifecycle cells 18

Phase 3では`src/loto/adapters/gluonts/p6_registry.py`をsource of truthとして、Broadのcanonical identityを壊さず9個のlibrary-specific Expanded identityへ分解します。

```text
Broad v1 canonical identity        = 1 (`gluonts-deepar`)
Expanded v2 implementation count   = 9
P6 isolated lane cells             = 9 × 2 = 18
```

| implementation_id | class |
|---|---|
| `gluonts-torch-deepnpts` | `DeepNPTSEstimator` |
| `gluonts-torch-deepar` | `DeepAREstimator` |
| `gluonts-torch-tide` | `TiDEEstimator` |
| `gluonts-torch-simplefeedforward` | `SimpleFeedForwardEstimator` |
| `gluonts-torch-temporalfusiontransformer` | `TemporalFusionTransformerEstimator` |
| `gluonts-torch-wavenet` | `WaveNetEstimator` |
| `gluonts-torch-dlinear` | `DLinearEstimator` |
| `gluonts-torch-patchtst` | `PatchTSTEstimator` |
| `gluonts-torch-lagtst` | `LagTSTEstimator` |

各identityは`algorithm_id` / `implementation_id`を分離し、P6 registryのsource path、official source tags、distribution/trainer、CPU resource contractへ結びます。

登録だけではruntime-certifiedにしません。新しい9 identityの初期値は明示的に次です。

```text
source_declared=true
runtime_status=NOT_RUN
runtime_certified=false
```

Draft PR #309 exact head `edba730a4f2c944c1ccc0bee510f7ce34833b6c3` ではlatest 9/9 + compat 9/9 = **18/18 CPU lifecycle VERIFIED**、P7D `VALID/VERIFIED`、`p8_eligible=true` の別証拠があります。しかし#309はmain未統合なので、この証拠をPhase 3 inventoryへ`runtime_certified=true`としてコピーしません。

詳細: [`docs/gluonts/GLUONTS_EXPANDED_V2_PHASE3.md`](docs/gluonts/GLUONTS_EXPANDED_V2_PHASE3.md)

---

## 5. sktime — Broad 1 / registry 141 / formal P1 4

```text
sktime = 1.0.1
Broad v1 umbrella = 1
registry discovered/importable = 141
core-compatible = 53
optional-dependency-declared = 88
formal P1 models = 4
```

formal P1 4モデルはfit/predict/save-load/formal verification PASSですが、141全件runtime-certifiedではありません。Expanded v2へのdeterministic identity integrationは#289 / TAJ-32で継続します。

---

## 6. Darts / ReservoirPy の「1」

### Darts

Broad v1は1 umbrellaですが、current documentationでは58 public forecasting exportsをPhase 2 inventory対象として扱っています。local exact worktreeではNLinear/DLinear actual GPU fit/predict evidenceがありますが、58全件standalone/runtime-certifiedという意味ではありません。

### ReservoirPy

Broad v1は1 ESN identityですが、#294はReservoir/NVAR/IPReservoir/ES2N等のscientifically distinct pipelinesを、Cartesian-product inflationを避けてExpanded v2へ追加する作業を要求しています。final countは未freezeです。

---

## 7. 主要ライブラリ / 実行面

| Library | Inventory view | Execution surface | Runtime evidence | OOF |
|---|---|---|---|---|
| sklearn Broad | 7 | Broad campaign | tree-specific | 未完 |
| sklearn dynamic | installed-version dependent | `loto-sklearn` | provider/certify surface | 未完 |
| XGBoost | Broad 1 | resource-aware Broad campaign | CUDA exact-source VERIFIED | 未完 |
| CatBoost | Broad 1 | resource-aware Broad campaign | GPU exact-source VERIFIED | 未完 |
| LightGBM | Broad 2 | resource-aware Broad campaign | OpenCL GPU VERIFIED / CUDA tree learner not certified | 未完 |
| StatsForecast | Broad 41 | shared 8 + campaign | lifecycle + development evidence | 部分実行 |
| MLForecast | Auto 8 | direct 2 + Auto | backend dependent | 未完 |
| NeuralForecast fixed | 37 | shared subset + dedicated | GPU capable | 未完 |
| NeuralForecast Auto | 36 | AutoModel runner | Ray/Optuna/GPU | 未完 |
| AutoGluon | Broad 1 / Expanded 37 | isolated | backend dependent | 未完 |
| Darts | Broad 1 / source surface 58 | provider/campaign | local bounded GPU evidence | 未完 |
| GluonTS | Broad 1 / Expanded 9 / lane cells 18 | shared + isolated P6 provider | #309 exact-head CPU lifecycle | 未完 |
| sktime | Broad 1 / registry 141 | isolated | formal P1 4 PASS | 未完 |
| skforecast | Broad 1 / evidence plan 18 / committed Expanded 1 | repository integration pending | operator-local mixed evidence | 未完 |
| ReservoirPy | Broad 1 | optional/shared | partial | 未完 |
| TSFM | 21 | provider-specific | retained 19/21 certified | 未完 |
| probabilistic | effective 76 | separate catalog/run/API | backend-specific | combined planner未実装 |

---

## 8. Recent implementation/documentation boundary

| PR | SHA / status | Scope |
|---|---|---|
| #293 | `f04cd876...` | Expanded v2 foundation + AutoGluon 37 |
| #301 | `3cc73dba...` | dynamic sklearn provider |
| #302 | `7d75dadc...` | parallel Broad campaign orchestration |
| #304 | `de1444af...` | XGBoost/CatBoost GPU routing |
| #305 | `a03053ea...` | LightGBM accelerator probe |
| #306 | `feb4ea5e...` | LightGBM OpenCL GPU routing |
| #307 | `ed7d6c81...` | sktime P1 normalization |
| #310 | `4f4f8579...` | current-state docs + skforecast operator evidence |
| #312 | `063120fd...` | library/model matrix alignment |
| #311 | `9623f2a5...` | Darts evidence + Broad planner boundary |
| #313 | `0fb8d2e9...` | README audit-boundary stabilization |
| #314 | `dfd9aa6e...` | current status/history alignment |
| #315 | `770d5b97...` | GluonTS Broad 1 vs registry 9 vs lifecycle 18 clarity |
| #316 | `eb988d29...` | umbrella Broad / Expanded / observed count boundary clarification |
| #309 | Draft | GluonTS P6/P7 CPU lifecycle repair; exact-head evidence is not current-main certification |

---

## 9. Scientific contract

Primary metric: **Hit@±1**.

Required companions:

- MAE / MSE / RMSE
- position-wise Hit@±1
- all-position Hit@±1

Required baselines:

- Random
- fixed
- mean
- median
- last/recent
- frequency
- statistical

Evaluation order:

```text
Train-only preprocessing / scaler / encoder / feature selection / HPO
-> chronological Validation / OOF
-> all configured seeds + mean / variance / worst
-> prediction SHA-256 seal + timestamp before actual read
-> explicit Holdout authorization
-> Holdout
-> sealed Prospective prediction
-> actual arrival / scoring
-> human promotion decision
```

Holdout=CLOSED. Prospective=CLOSED. Automatic promotion/retraining/registry write=FORBIDDEN.

---

## 10. Common commands

```bash
# six-game geometry
uv run loto3 games

# frozen Broad v1
uv run loto3 catalog --counts
uv run loto3 catalog

# shared ModelSpec
uv run loto models list

# Broad-only plan: 174 × 6 = 1,044
uv run loto3 campaign --output unused --plan-only

# separate probabilistic surface: effective 76
uv run loto3 probabilistic catalog-list

# derived Expanded v2 count; after GluonTS Phase 3 this must report 218
uv run python -c 'from loto.models.implementation_catalog import expanded_inventory_counts; print(expanded_inventory_counts())'

# dynamic sklearn
uv run loto-sklearn list
uv run loto-sklearn certify --kind all --seed 1 --output artifacts/sklearn-certification

# parallel Broad campaign
uv run python -m loto.evaluation.parallel_campaign --help

# sktime P1
ROOT="$PWD" SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p1_matrix_certification.sh

# NeuralForecast Auto
uv run loto neuralforecast automodel-run --help

# data acquisition
uv run loto data acquire --help
```

---

## 11. Source of truth

優先順位:

1. current code/configuration;
2. tests/workflows/repository-retained evidence;
3. exact PR/source evidence;
4. exact-source operator/local evidence with provenance;
5. merged PR/commit history;
6. live GitHub Issues / Linear state;
7. current documentation;
8. historical snapshots.

特にcountは次のcodeを優先します。

- `src/loto/models/catalog_full.py` — Broad v1
- `src/loto/models/implementation_catalog.py` — committed Expanded v2
- framework-specific registry/inventory modules — runtime/source denominators

異なる分母や異なるSHAの成功証拠を、1つの「model count」や「current-main VERIFIED」に混ぜません。
