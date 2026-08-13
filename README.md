# Loto Forecast Platform

**ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4**を対象に、統計モデル、機械学習、深層学習、AutoML、時系列基盤モデル（TSFM）、確率モデルを、時系列リークを防いだ共通契約で比較・検証・運用する研究プラットフォームです。

このREADMEは「何が実装されているか」「どの実行面まで確認できているか」「科学評価のどこまで進んでいるか」を最短で把握する入口です。

> **Documentation audit base:** `main@932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf` (2026-08-13)  
> **Latest merged boundary at audit start:** PR #308 — README current-state refresh  
> **Rule:** `REGISTERED != ROUTABLE != RUNTIME_CERTIFIED != OOF_EVALUATED != HOLDOUT_EVALUATED != PROSPECTIVE_EVALUATED != PROMOTION_ELIGIBLE`  
> package versionはREADMEへ手書きしません。`loto.version.__version__` / installed package metadata / `loto-build-info`を正本とします。

## まず見る資料

| 知りたいこと | 資料 |
|---|---|
| ライブラリ別モデル・引数・対応機能 | [`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md) |
| current state / open gates | [`docs/STATUS.md`](docs/STATUS.md) |
| 現在の検証境界 | [`docs/CURRENT_VERIFICATION_REPORT.md`](docs/CURRENT_VERIFICATION_REPORT.md) |
| 次に作業する人向け引継ぎ | [`docs/CURRENT_HANDOFF.md`](docs/CURRENT_HANDOFF.md) |
| 実行・運用機能 | [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md) |
| skforecast 0.23.0 operator runtime evidence | [`docs/SKFORECAST_RUNTIME_CERTIFICATION.md`](docs/SKFORECAST_RUNTIME_CERTIFICATION.md) |
| scikit-learn dynamic provider | [`docs/SKLEARN_ALL_MODELS.md`](docs/SKLEARN_ALL_MODELS.md) |
| 6ゲーム並列Unified Campaign | [`docs/PARALLEL_UNIFIED_CAMPAIGN.md`](docs/PARALLEL_UNIFIED_CAMPAIGN.md) |
| LightGBM GPU backend認証 | [`docs/LIGHTGBM_GPU_CERTIFICATION.md`](docs/LIGHTGBM_GPU_CERTIFICATION.md) |
| TSFM retained runtime evidence | [`docs/TSFM_RUNTIME_CAPABILITIES.md`](docs/TSFM_RUNTIME_CAPABILITIES.md) |
| 評価 / Hit@±1 / OOF | [`docs/evaluation/`](docs/evaluation/) |
| 運用 / 監視 | [`docs/operations/`](docs/operations/) |

---

## 1. 現在地

| 領域 | 状態 | 現在確認できること | まだ意味しないこと |
|---|---|---|---|
| 6ゲーム geometry | **VERIFIED** | positions・値域・select/digits契約 | 全モデル×全ゲーム完走ではない |
| Broad v1 | **VERIFIED** | frozen inventory **174** | 174全件runtime成功ではない |
| Unified v1 | **EXECUTION_PENDING** | **250 × 6 = 1500** planning units | 1500全成功ではない |
| Parallel Unified Campaign | **VERIFIED / PARTIALLY_VERIFIED** | game単位process並列、CPU affinity/thread制限、progress/aggregate artifacts | 全174×6 real-data完走ではない |
| Expanded v2 Phase 1 | **VERIFIED / PARTIALLY_VERIFIED** | AutoGluon umbrellaを37実装へ展開し **210 identities** | 210全件runtime-certifiedではない |
| scikit-learn dynamic provider | **VERIFIED / PARTIALLY_VERIFIED** | `loto-sklearn`、installed-version dynamic inventory、smoke/certify surface | 任意環境の全estimator成功保証ではない |
| Tree GPU routing | **VERIFIED** | XGBoost/CatBoost CUDA lane、LightGBM OpenCL GPU lane | 全ゲームOOF優位ではない |
| LightGBM CUDA | **NOT CERTIFIED / FAIL-CLOSED** | resolved buildはOpenCL `device_type="gpu"`で認証 | CUDA tree learner対応を意味しない |
| StatsForecast | **VERIFIED / PARTIALLY_VERIFIED** | Broad 41 / shared 8 / lifecycle + real-game dev lane | 41×6完走ではない |
| NeuralForecast fixed | **VERIFIED / PARTIALLY_VERIFIED** | Broad 37 / direct shared subset 17 | 37全件runtime/OOF完了ではない |
| NeuralForecast Auto | **VERIFIED / PARTIALLY_VERIFIED** | official 36、Ray/Optuna、seed/precision/GPU evidence path | 36×6正式認証完了ではない |
| MLForecast | **PARTIALLY_VERIFIED** | Auto 8 / direct shared 2 | Auto 8 = shared workers 8ではない |
| AutoGluon TimeSeries | **PARTIALLY_VERIFIED** | source 29 + unique ensembles 8 = expanded 37 | 37全件runtime-certifiedではない |
| sktime | **PARTIALLY_VERIFIED** | registry 141 discovered/importable、P1固定4モデルのfit/predict/save-load/formal verification PASS | 141全件runtime-certifiedではない |
| skforecast | **PARTIALLY_VERIFIED / OPERATOR_LOCAL_EVIDENCE** | 0.23.0 core、RNN、Chronos-2、TimesFM 2.5、TabICLなどの実推論証拠あり | current-main正式provider/catalog統合や全Expanded inventory完了ではない |
| TSFM retained audit | **PARTIALLY_VERIFIED** | retained 21 identities中19 runtime CERTIFIED / 2 BLOCKED | 全19がlottery-compatible/OOF済みではない |
| Probabilistic platform | **VERIFIED / PARTIALLY_VERIFIED** | separate catalog/backend/run/API surface | 全モデル科学評価完了ではない |
| Holdout | **CLOSED** | explicit authorizationまで閉鎖 | development結果から自動解禁されない |
| Prospective | **CLOSED** | future prediction seal後のみ評価可能 | Holdout未承認で自動進行しない |
| Automatic promotion | **FORBIDDEN** | human approval前提 | runtime PASSだけでchampion化しない |

### 状態語

| status | 意味 |
|---|---|
| `VERIFIED` | current code / tests / retained evidenceで主張を確認済み |
| `PARTIALLY_VERIFIED` | 一部モデル・lane・環境・証拠のみ成立 |
| `OPERATOR_LOCAL_EVIDENCE` | maintainer hostで得たexact-source runtime証拠。current-main retained certificationとは別クラス |
| `EXECUTION_PENDING` | 実装/計画はあるが対象分母を完走していない |
| `BLOCKED` | dependency / license / runner / policy / artifact等の明示gateで停止 |
| `NOT CERTIFIED` | 成功証拠がなくfail-closedで扱う |

---

## 2. Broad v1 = 174 のライブラリ内訳

Broad v1は凍結された科学比較分母です。Expanded/dynamic inventoryを174へ足し戻しません。

| Library | Count |
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
| Darts | 1 |
| GluonTS | 1 |
| ReservoirPy | 1 |
| sktime | 1 |
| skforecast | 1 |
| **TOTAL** | **174** |

別分母:

- scikit-learn dynamic denominator: installed versionの`all_estimators()`
- sktime registry denominator: current isolated laneでは141 forecasters discovered/importable
- Expanded v2 implementation identities
- Time-Series-Library / BasicTS / Merlion
- separate probabilistic catalog

---

## 3. 主要ライブラリ / 実行面

| Library | Inventory | Shared / provider | HPO | GPU | runtime evidence | 全ゲームOOF |
|---|---:|---|:---:|---|---|---|
| scikit-learn Broad | 7 | candidate / position / Unified Campaign | — | tree-specific | 部分検証 | 未完 |
| scikit-learn dynamic | version-dependent | `loto-sklearn` provider | — | estimator依存 | provider surface verified | 未完 |
| XGBoost | Broad 1 | resource-aware campaign | — | **CUDA VERIFIED** | exact-head GPU runtime | 未完 |
| CatBoost | Broad 1 | resource-aware campaign | — | **GPU VERIFIED** | exact-head GPU runtime | 未完 |
| LightGBM | Broad 2 | resource-aware campaign | — | **OpenCL GPU VERIFIED** | classifier + position verified | 未完 |
| StatsForecast | 41 | shared 8 + campaign | model内Auto | CPU中心 | 部分検証 | 未完 |
| MLForecast | Auto 8 | direct shared 2 | ✓ | backend依存 | 部分検証 | 未完 |
| NeuralForecast fixed | 37 | shared subset 17 | — | ✓ | 部分検証 | 未完 |
| NeuralForecast Auto | 36 | dedicated runner | Ray / Optuna | ✓ | 部分検証 | 未完 |
| AutoGluon | umbrella 1 / expanded 37 | isolated provider | AutoML | backend依存 | 部分検証 | 未完 |
| HierarchicalForecast | 10 methods | reconciliation | — | — | capability verified | base forecast依存 |
| TSFM | 21 retained audit ids | provider-specific | — | model依存 | retained 19/21 certified | 未完 |
| sktime | Broad 1 / registry 141 | isolated campaign | estimator依存 | estimator依存 | P1 4-model formal PASS | 未完 |
| skforecast | Broad 1 | repository integration pending; upstream wrapper surface separately exercised | Optuna/search surface | estimator/model依存 | **operator-local partial runtime evidence** | 未完 |

詳細モデル表は[`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md)を参照してください。

---

## 4. skforecast 0.23.0 — 今回追加した事実関係

GitHub Issue #289 / Linear TAJ-32のExpanded v2実装前調査として、maintainer hostでskforecast 0.23.0を実行しました。runtime source headは`9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd`であり、現在のmain SHAとは異なります。

### 実行できた主要surface

- `ForecasterRecursive`: Ridge + exog、HistGradientBoosting、LightGBM、XGBoost、CatBoost
- `ForecasterDirect`: Ridge
- `ForecasterRecursiveMultiSeries`
- `ForecasterDirectMultiVariate`
- `ForecasterEquivalentDate`
- `ForecasterStats + ARAR`
- Rolling / Calendar features
- `TimeSeriesFold` / backtesting
- Optuna search
- save/load round-trip
- drift detector
- bootstrap / calibrated intervals
- `ForecasterRnn`: LSTM / GRU GPU、LSTM CPU fallback

### Foundation adapter evidence

| implementation | current operator result | important boundary |
|---|---|---|
| Chronos-2 small | **GPU + CPU PASS**、exog/point/interval | HF revision observed, repository pin/routingは別gate |
| TimesFM 2.5 | **GPU + CPU PASS**、point/interval/quantiles | adapterはexog非対応。model revision enforcementは別gate |
| Moirai-2 small | **runtime PASS under compatibility override** | declared dependency conflictのためnormal routability **BLOCKED** |
| TabICL v2 | **GPU + CPU + exog + interval + quantile PASS** | checkpoint bytes/revision/SHA-256もverified |
| TabPFN-TS v3 path | adapter/exog/device setup PASS | inferenceは**INVALID_OR_EXPIRED_TOKEN / LICENSE_AUTHでBLOCKED** |
| T0 | not executed in this sequence | pending |

TabICL checkpoint evidence:

```text
repo = jingang/TabICL
revision = 4dcd344ece2c00be9e831fdd35bed57b5ad83e19
file = tabicl-regressor-v2-20260212.ckpt
size = 114324594 bytes
sha256 = 0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a
```

TabPFN-TS current blocker:

```text
requested checkpoint = tabpfn-v3-regressor-v3_20260506_timeseries.ckpt
license = tabpfn-3-license-v1.0
token_valid = false
license_accepted = not evaluated
runtime inference = NOT_EXECUTED
```

詳細: [`docs/SKFORECAST_RUNTIME_CERTIFICATION.md`](docs/SKFORECAST_RUNTIME_CERTIFICATION.md)

**このoperator-local evidenceを、Broad `skforecast-recursive` のcurrent-main正式runtime certificationやExpanded v2完了と読み替えません。**

---

## 5. 2026-08-12〜13の主要merge

| PR | Main SHA | 主な変更 |
|---|---|---|
| #268 | `81bd4f81...` | statistical / causal analysis foundation |
| #270 | `775274cc...` | runtime audit serialization + resource-aware broad runner |
| #273 | `522253ea...` | repository observability dashboard / structured intake |
| #274 | `c57731e1...` | evidence-aware visual dashboard + Pages gate |
| #276 | `4eabd68d...` | repository control center / workflow classification |
| #277 | `1df090fa...` | scheduler stabilization: fingerprint/GPU assignment/process cleanup/worker cap |
| #293 | `f04cd876...` | Expanded v2 foundation + AutoGluon 37 identities |
| #295 | `951f5f57...` | Toto 2.0 family manifest + 22M provenance gate |
| #296 | `abe7e02c...` | Toto 22M certification infrastructure; native-Linux formal gate separate |
| #299 | `05eba49d...` | README implementation fact-check |
| #300 | `a7eb50ca...` | library/model compatibility matrix |
| #301 | `3cc73dba...` | dynamic all-estimator scikit-learn provider |
| #302 | `7d75dadc...` | parallel Unified Campaign + live progress |
| #303 | `b9be4174...` | isotonic calibrated logistic route |
| #304 | `de1444af...` | XGBoost/CatBoost GPU lease routing |
| #305 | `a03053ea...` | LightGBM fail-closed accelerator probe |
| #306 | `feb4ea5e...` | LightGBM OpenCL GPU routing |
| #307 | `ed7d6c81...` | sktime P1 input-contract normalization |
| #308 | `932977f7...` | README current-state reconciliation |

---

## 6. 6ゲーム共通契約

| game | family | positions | values | semantics |
|---|---|---:|---|---|
| `mini` | select | 5 | 1..31 | 昇順・重複なし |
| `loto6` | select | 6 | 1..43 | 昇順・重複なし |
| `loto7` | select | 7 | 1..37 | 昇順・重複なし |
| `bingo5` | select | 8 | 1..40 | geometry contractに従う |
| `numbers3` | digits | 3 | 0..9 | 順序あり・重複可 |
| `numbers4` | digits | 4 | 0..9 | 順序あり・重複可 |

`available=true`、import成功、単一smokeだけでは6ゲーム対応・runtime certification・forecast skillを意味しません。

---

## 7. 科学評価契約

| 項目 | contract |
|---|---|
| primary metric | **Hit@±1** |
| secondary | MAE / MSE / RMSE / position-wise Hit@±1 / all-position Hit@±1 |
| baselines | Random / fixed / mean / median / recent / frequency / statistical |
| split | chronological Train / Validation / Holdout / Prospective |
| preprocessing / HPO | Train内だけでfit |
| seeds | 全設定seedを保持し平均・分散・worstを保存 |
| prediction lock | actual判明前にSHA-256 + timestampで固定 |
| Holdout | explicit authorization only |
| Prospective | sealed future prediction + later actual |
| promotion | human approval; automatic promotion forbidden |

確認順序:

```text
source-declared
-> registered
-> routable
-> dependency/version verified
-> load/input/inference
-> shape/finite/device/PID/VRAM/fallback
-> lifecycle/save-reload when applicable
-> runtime-certified
-> lottery-compatible
-> chronological development OOF
-> Holdout
-> Prospective
-> promotion eligibility
-> human approval
```

---

## 8. よく使うコマンド

```bash
# geometry / inventories
uv run loto3 games
uv run loto3 catalog --counts
uv run loto3 catalog
uv run loto models list

# model × game planning
uv run loto3 campaign --output unused --plan-only

# parallel Unified Campaign
uv run python -m loto.evaluation.parallel_campaign --help

# dynamic sklearn
uv run loto-sklearn list
uv run loto-sklearn smoke --model RandomForestRegressor --seed 1
uv run loto-sklearn certify --kind all --seed 1 --output artifacts/sklearn-certification

# sktime P1
ROOT="$PWD" SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p1_matrix_certification.sh

# NeuralForecast Auto
uv run loto neuralforecast automodel-run --help

# probabilistic
uv run loto3 probabilistic catalog-list
uv run loto3 probabilistic backends

# data acquisition
uv run loto data acquire --help
```

---

## 9. Source of truth

実装状態はMarkdown単独で判定しません。

1. current code / configuration
2. tests / workflows / repository-retained artifacts
3. exact-source operator/local runtime evidence with environment provenance
4. merged PR / commit history
5. live GitHub Issues / Linear project state
6. current-state documentation
7. historical documentation snapshots

PR/worktree/local runの成功はそのsource SHAに対する証拠です。異なるSHAの成功証拠を「current mainで同一条件 VERIFIED」と混ぜません。

現在の主要open gateは[`docs/STATUS.md`](docs/STATUS.md)を参照してください。
