# Loto Forecast Platform

**ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4**を対象に、統計モデル、機械学習、深層学習、AutoML、時系列基盤モデル（TSFM）、確率モデルを、時系列リークを防いだ共通契約で比較・検証・運用する研究プラットフォームです。

このREADMEは「何が実装されているか」「どの分母を見ているか」「どこまでruntime/scientific evidenceがあるか」を最短で把握する入口です。

> **Phase 4A candidate base:** `main@45bcf60fa04fc3736e3a73760039254573abf4c8` (after GluonTS PR #323, 2026-08-13)  
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
| Expanded v2 | **PHASE 4A CANDIDATE / SOURCE-BACKED** | AutoGluon 37 + GluonTS 9 + skforecast 27を含むderived total **244** | 244全件runtime-certified、最終inventory freezeではない |
| scikit-learn dynamic | **VERIFIED / PARTIALLY_VERIFIED** | installed-version discovery / smoke / certify | 全estimator成功保証ではない |
| StatsForecast | **VERIFIED / PARTIALLY_VERIFIED** | Broad 41 / shared 8 / development evidence | Holdout/Prospectiveではない |
| NeuralForecast fixed | **VERIFIED / PARTIALLY_VERIFIED** | Broad 37 / shared subset 17 | 37全件OOF完了ではない |
| NeuralForecast Auto | **VERIFIED / PARTIALLY_VERIFIED** | official 36 / Ray / Optuna / GPU evidence path | 36×6 formal完了ではない |
| AutoGluon | **EXPANDED 37 / PARTIAL RUNTIME** | 29 source models + 8 unique ensembles | 37全件runtime-certifiedではない |
| Darts | **BROAD 1 / SOURCE SURFACE >1** | 58 public forecasting exportsをPhase 2で調査、local NLinear/DLinear GPU evidence | 58全件standalone/runtime-certifiedではない |
| GluonTS | **BROAD 1 / EXPANDED 9** | P6 registryの9 estimatorをExpanded identityへ統合。Draft #309 exact-headは2 lanes × 9 = 18/18 CPU lifecycle VERIFIED | 18 unique modelsではない。#309 main統合/GPU/OOFではない |
| sktime | **BROAD 1 / REGISTRY 141** | 141 discovered/importable、53 core-compatible、88 optional、formal P1=4 | 141全件runtime-certifiedではない |
| skforecast | **BROAD 1 / EXPANDED 27 CANDIDATE** | pinned 0.23.0 sourceからreviewed 27 identitiesを固定 | 27 runtime-certifiedではない。15 operator-local PASS / 2 BLOCKED / 10 NOT_RUN |
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

| Library | Broad v1 | Expanded v2 candidate | Other denominator | Current gate |
|---|---:|---:|---|---|
| AutoGluon | 1 | **37** | 29 base + 8 unique ensembles | merged |
| Darts | 1 | **1** | **58 public forecasting exports** | #286 / TAJ-27 open |
| GluonTS | 1 | **9** | **9 estimator algorithms**, 2 isolated lanes = **18 lifecycle cells** | #323 merged; runtime gate separate |
| ReservoirPy | 1 | **1** | final distinct count未freeze | #294 open |
| sktime | 1 | **1** | **141 discovered/importable** | #289 / TAJ-32 Phase 4B open |
| skforecast | 1 | **27** | **27 reviewed source-backed identities** | PR #324 Phase 4A; formal repository runtime certificationは別 |

### 2.3 current candidate total

```text
Broad v1                                      = 174
Probabilistic effective v1                    = 76
Combined Broad + Probabilistic accounting     = 250
Current Broad campaign planner                = 174 × 6 = 1,044
Combined accounting × six games               = 250 × 6 = 1,500
Expanded v2 current main after GluonTS         = 218
Expanded v2 with skforecast Phase 4A candidate = 244
```

```text
218 - skforecast Broad copy 1 + skforecast implementations 27 = 244
```

Darts / ReservoirPy / sktime / Time-Series-Library / BasicTSの分解はまだ244へ入っていないため、**244はExpanded v2の最終freeze値ではありません**。

詳細: [`docs/INVENTORY_COUNT_BOUNDARIES.md`](docs/INVENTORY_COUNT_BOUNDARIES.md)

---

## 3. skforecast — Broad 1 / Expanded 27 candidate

Phase 4Aはoperator evidenceだけでなく、固定したupstream source `skforecast v0.23.0` を再監査してmanifestを作ります。

```text
package = skforecast==0.23.0
upstream_tag = v0.23.0
upstream_commit = c881d5d350426985c1c31373077b7d5b620f233d
operator_evidence_head = 9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd
```

Pinned source confirms:

- recursive exports: `ForecasterEquivalentDate`, `ForecasterRecursive`, `ForecasterRecursiveClassifier`, `ForecasterRecursiveMultiSeries`, `ForecasterStats`;
- direct exports: `ForecasterDirect`, `ForecasterDirectMultiVariate`;
- deep-learning strategy: `ForecasterRnn`;
- foundation strategy: `ForecasterFoundation` / `FoundationModel`;
- `ForecasterStats` explicitly supports **7 statistical implementations**;
- `FoundationModel` explicitly lists **8 selectable model IDs** including three Chronos-2 IDs.

無限のwrapper × arbitrary sklearn estimator Cartesian productは作りません。

| Group | Count | Evidence boundary |
|---|---:|---|
| Recursive regression families | 5 | OPERATOR_LOCAL_PASS |
| Recursive classifier representative binding | 1 | SOURCE_DECLARED / NOT_RUN |
| Direct Ridge | 1 | OPERATOR_LOCAL_PASS |
| Recursive multi-series Ridge | 1 | OPERATOR_LOCAL_PASS |
| Direct multivariate Ridge | 1 | OPERATOR_LOCAL_PASS |
| EquivalentDate | 1 | OPERATOR_LOCAL_PASS |
| ForecasterStats supported implementations | 7 | ARAR PASS / other 6 NOT_RUN |
| RNN LSTM / GRU | 2 | OPERATOR_LOCAL_PASS |
| Foundation explicit model IDs | 8 | mixed PASS / BLOCKED / NOT_RUN |
| **Total** | **27** | **15 PASS / 2 BLOCKED / 10 NOT_RUN** |

全27 rowで `runtime_certified=false` を維持します。Moirai-2はnormal dependency routeがBLOCKED、TabPFN-TS v3はinvalid/expired authenticationでcheckpoint取得前に停止、source-only追加rowはNOT_RUNです。

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

Draft PR #309 exact headの18/18 CPU lifecycle VERIFIEDは別evidence classであり、inventory登録だけでruntime-certifiedへ昇格させません。

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

formal P1 4モデルはfit/predict/save-load/formal verification PASSですが、141全件runtime-certifiedではありません。Phase 4Bではexact 141-row manifestを固定し、wrapper/composite/adapterと独立forecasterを分類してからExpanded v2へ統合します。

---

## 6. Darts / ReservoirPy の「1」

Darts Broad v1は1 umbrellaですが、58 public forecasting exportsをPhase 2 inventory対象として調査中です。ReservoirPyもBroad v1は1ですが、#294でscientifically distinct pipelinesのExpanded化を追跡しています。

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
| sktime | Broad 1 / registry 141 / Expanded 1 | isolated | formal P1 4 PASS | 未完 |
| skforecast | **Broad 1 / Expanded 27 candidate** | Expanded inventory; routing separate | 15 local PASS / 2 blocked / 10 not-run | 未完 |
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
| #307 | `ed7d6c81...` | sktime P1 normalization |
| #310 | `4f4f8579...` | current-state docs + skforecast operator evidence |
| #315 | `770d5b97...` | GluonTS count clarity |
| #316 | `eb988d29...` | umbrella count boundary clarification |
| #323 | `45bcf60f...` | GluonTS 9 Expanded identities merged |
| #324 | open | skforecast 27 Phase 4A candidate; CI gate pending |
| #309 | Draft | GluonTS P6/P7 runtime repair exact-head evidence |

---

## 9. Scientific contract

Primary metric: **Hit@±1**.

Required companions: MAE / MSE / RMSE / position-wise Hit@±1 / all-position Hit@±1.

Required baselines: Random / fixed / mean / median / last/recent / frequency / statistical.

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
uv run loto3 games
uv run loto3 catalog --counts
uv run loto models list

# Broad-only plan: 174 × 6 = 1,044
uv run loto3 campaign --output unused --plan-only

# Expanded v2 Phase 4A candidate must report 244
uv run python -c 'from loto.models.implementation_catalog import expanded_inventory_counts; print(expanded_inventory_counts())'

# sktime P1
ROOT="$PWD" SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p1_matrix_certification.sh
```

---

## 11. Source of truth

1. current code/configuration;
2. tests/workflows/repository-retained evidence;
3. exact PR/source evidence;
4. exact-source operator/local evidence with provenance;
5. merged PR/commit history;
6. live GitHub Issues / Linear state;
7. current documentation;
8. historical snapshots.

Count authorityは `catalog_full.py`（Broad v1）、`implementation_catalog.py` + pinned manifests（Expanded v2）、framework-specific registry（別分母）を分離して読みます。
