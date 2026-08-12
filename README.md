# Loto Forecast Platform

**ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4**を対象に、統計モデル、機械学習、深層学習、AutoML、時系列基盤モデル（TSFM）、確率モデルを、時系列リークを防いだ共通契約で比較・検証・運用する研究プラットフォームです。

このREADMEは「何が使えるか」を最短で把握する入口です。モデル・ライブラリ別の詳細は専用対応表へ分離しました。

> **Implementation audit base:** `main@05eba49dad8c0700c303783267784cfde081e419` (2026-08-12)  
> **Rule:** `REGISTERED != ROUTABLE != RUNTIME_CERTIFIED != OOF_EVALUATED != HOLDOUT_EVALUATED != PROSPECTIVE_EVALUATED != PROMOTION_ELIGIBLE`  
> 現在のpackage versionはREADMEへ手書きしません。canonical versionは`loto.version.__version__` / installed package metadata / `loto-build-info`を正本とします。

## まず見る資料

| 知りたいこと | 資料 |
|---|---|
| ライブラリごとのモデル一覧・引数・対応機能・実装状況 | **[`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md)** |
| 実行コマンド・機能の詳細 | [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md) |
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
| Expanded v2 Phase 1 | **VERIFIED / PARTIALLY_VERIFIED** | **210 identities**。AutoGluon umbrellaを37実装へ展開 | 210全件runtime-certifiedではない |
| StatsForecast | **VERIFIED / PARTIALLY_VERIFIED** | Broad 41 / shared explicit 8 / lifecycle + real-game dev lane | 41×6完走ではない |
| NeuralForecast fixed | **VERIFIED / PARTIALLY_VERIFIED** | Broad 37 / direct shared subset 17 | 37全件runtime/OOF完了ではない |
| NeuralForecast Auto | **VERIFIED / PARTIALLY_VERIFIED** | official 36 / Ray・Optuna / seed・precision・GPU evidence path | 36×6正式認証完了ではない |
| MLForecast | **PARTIALLY_VERIFIED** | Auto inventory 8 / direct shared 2 | Auto 8 = shared workers 8ではない |
| AutoGluon TimeSeries | **PARTIALLY_VERIFIED** | source 29 models + 8 unique ensembles = 37 expanded identities | 37全件runtime-certifiedではない |
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
| sktime | 1 | forecasting framework | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#12-darts--gluonts--reservoirpy--sktime--skforecast) |
| skforecast | 1 | recursive lag ML | [対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md#12-darts--gluonts--reservoirpy--sktime--skforecast) |
| **TOTAL** | **174** |  | frozen denominator |

Broad v1外には Time-Series-Library、BasicTS、Merlion、separate probabilistic 72-model catalog等があります。これらも[専用対応表](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md)へ記載しています。

---

## 3. 主要ライブラリの対応関係

| Library | Inventory | Shared route | Provider / isolated | HPO | GPU | runtime evidence | 全ゲームOOF |
|---|---:|---|---|:---:|:---:|---|---|
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
| sktime | 1 Broad | — | isolated campaign | framework依存 | framework依存 | **EXECUTION_PENDING** | **未完** |
| skforecast | 1 Broad | — | pending | — | regressor依存 | **EXECUTION_PENDING** | **未完** |

モデル名、class、主要引数、capabilityの詳細は **[`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md)** を参照してください。

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
   - framework-specific campaign / provider modules
2. tests / workflows / retained runtime artifacts
3. merged PR / commit history
4. live Linear project state
5. documentation

詳細資料:

- **[`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md)**
- [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md)
- [`docs/TSFM_RUNTIME_CAPABILITIES.md`](docs/TSFM_RUNTIME_CAPABILITIES.md)
- [`docs/evaluation/`](docs/evaluation/)
- [`docs/operations/`](docs/operations/)
