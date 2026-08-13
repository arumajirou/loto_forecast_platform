# Loto Forecast Platform

**ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4**を対象に、統計モデル、機械学習、深層学習、AutoML、時系列基盤モデル（TSFM）、確率モデルを、時系列リークを防いだ共通契約で比較・検証・運用する研究プラットフォームです。

このREADMEは「何が実装されているか」「どの実行面まで確認できているか」「科学評価のどこまで進んでいるか」を最短で把握する入口です。

> **Evidence audit source base before documentation alignment:** `main@063120fd9b07d07548442edbce480a6d068f9f43` (PR #312, 2026-08-13)  
> **Documentation alignment:** PR #311 — merged as `9623f2a562d21b4f9be84c392429885a51a72fe1`  
> **Open boundary:** Draft PR #309 — GluonTS P6/P7 CPU lifecycle certification; main未統合  
> **Local-only boundary:** Darts Torch dependency/profile/lock + NLinear/DLinear GPU evidenceはmain未反映  
> **Rule:** `REGISTERED != ROUTABLE != RUNTIME_CERTIFIED != OOF_EVALUATED != HOLDOUT_EVALUATED != PROSPECTIVE_EVALUATED != PROMOTION_ELIGIBLE`

## まず見る資料

| 知りたいこと | 資料 |
|---|---|
| ライブラリ別モデル・引数・対応機能 | [`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md) |
| current state / open gates | [`docs/STATUS.md`](docs/STATUS.md) |
| 現在の検証境界 | [`docs/CURRENT_VERIFICATION_REPORT.md`](docs/CURRENT_VERIFICATION_REPORT.md) |
| 次に作業する人向け引継ぎ | [`docs/CURRENT_HANDOFF.md`](docs/CURRENT_HANDOFF.md) |
| 実行・運用機能 | [`docs/CAPABILITIES_AND_OPERATIONS.md`](docs/CAPABILITIES_AND_OPERATIONS.md) |
| Darts current state | [`docs/darts/CURRENT_STATE_DARTS.md`](docs/darts/CURRENT_STATE_DARTS.md) |
| skforecast operator-local evidence | [`docs/SKFORECAST_RUNTIME_CERTIFICATION.md`](docs/SKFORECAST_RUNTIME_CERTIFICATION.md) |
| dynamic sklearn | [`docs/SKLEARN_ALL_MODELS.md`](docs/SKLEARN_ALL_MODELS.md) |
| parallel Unified Campaign | [`docs/PARALLEL_UNIFIED_CAMPAIGN.md`](docs/PARALLEL_UNIFIED_CAMPAIGN.md) |
| LightGBM GPU | [`docs/LIGHTGBM_GPU_CERTIFICATION.md`](docs/LIGHTGBM_GPU_CERTIFICATION.md) |
| TSFM | [`docs/TSFM_RUNTIME_CAPABILITIES.md`](docs/TSFM_RUNTIME_CAPABILITIES.md) |

---

## 1. 現在地

| 領域 | 状態 | 現在確認できること | まだ意味しないこと |
|---|---|---|---|
| 6ゲーム geometry | **VERIFIED** | positions・値域・select/digits契約 | 全モデル×全ゲーム完走ではない |
| Broad v1 | **VERIFIED** | frozen inventory **174** | 174全件runtime成功ではない |
| Probabilistic v1 | **VERIFIED / PARTIALLY_VERIFIED** | current effective catalog **76** | current Broad plannerへ自動結合されるわけではない |
| Unified v1 | **ACCOUNTING / EXECUTION_PENDING** | combined denominator **250 = 174 + 76**、6ゲーム換算 **1,500** | current `loto3 campaign --plan-only` が1,500行を生成する意味ではない |
| Broad campaign planner | **VERIFIED CONTRACT** | current `loto3 campaign` planは **174 × 6 = 1,044** units | probabilistic 76を含まない |
| Parallel Unified Campaign | **VERIFIED / PARTIALLY_VERIFIED** | game単位process並列、CPU affinity/thread制限、progress/aggregate artifacts | current plannerがBroad+probabilisticを自動結合する意味ではない |
| Expanded v2 Phase 1 | **MERGED / VERIFIED inventory** | AutoGluon 29 base + 8 unique ensembles = 37、Phase 1 **210 identities** | 210全件runtime-certifiedではない |
| scikit-learn dynamic provider | **VERIFIED / PARTIALLY_VERIFIED** | `loto-sklearn`、installed-version dynamic inventory、smoke/certify surface | 任意環境の全estimator成功保証ではない |
| Tree GPU routing | **VERIFIED** | XGBoost/CatBoost GPU、LightGBM OpenCL GPU | 全ゲームOOF優位ではない |
| LightGBM CUDA | **NOT CERTIFIED** | current buildはOpenCL `device_type="gpu"`で認証 | CUDA tree learner対応ではない |
| StatsForecast | **VERIFIED / PARTIALLY_VERIFIED** | Broad 41、shared 8、lifecycle + six-game development evidence | Holdout/Prospectiveではない |
| NeuralForecast fixed | **VERIFIED / PARTIALLY_VERIFIED** | Broad 37 / shared subset 17 | 37全件runtime/OOF完了ではない |
| NeuralForecast Auto | **VERIFIED / PARTIALLY_VERIFIED** | official 36、Ray/Optuna、seed/precision/GPU evidence path | 36×6正式認証完了ではない |
| AutoGluon | **PARTIALLY_VERIFIED** | Expanded v2 source inventory 37 | source declaration != runtime certification |
| Darts | **LOCAL_VERIFIED / PUBLICATION_PENDING** | local Torch 2.9.1+cu130 bootstrap PASS、NLinear/DLinear actual GPU fit/predict VERIFIED | main反映、58 exports全件standalone/runtime-certifiedではない |
| GluonTS | **DRAFT #309 / EXACT-HEAD VERIFIED / MAIN PENDING** | 2 isolated lanes × 9 = 18 CPU lifecycle exact-head VERIFIED | main統合、GPU、OOFではない |
| sktime | **PARTIALLY_VERIFIED** | 141 discovered/importable、P1固定4 formal PASS | 141全件runtime-certifiedではない |
| skforecast | **PARTIALLY_VERIFIED / OPERATOR_LOCAL_EVIDENCE** | 0.23.0 core/RNN/foundation runtime evidence | current-main Expanded v2 integration完了ではない |
| TSFM | **PARTIALLY_VERIFIED** | retained 21中19 CERTIFIED / 2 BLOCKED | 全19 OOF済みではない |
| Holdout | **CLOSED** | explicit authorizationまで閉鎖 | development結果から自動解禁されない |
| Prospective | **CLOSED** | sealed future predictionのみ | Holdout未承認で自動進行しない |
| Automatic promotion | **FORBIDDEN** | human approval前提 | runtime PASSだけでchampion化しない |

### 状態語

| status | 意味 |
|---|---|
| `VERIFIED` | current code / tests / retained evidenceで確認 |
| `PARTIALLY_VERIFIED` | 一部identity/lane/environmentのみ成立 |
| `OPERATOR_LOCAL_EVIDENCE` | maintainer host exact-source evidence、current-main retained certificationとは別 |
| `LOCAL_VERIFIED` | local exact worktreeで成立、main未反映 |
| `PUBLICATION_PENDING` | branch/PR/main反映待ち |
| `EXECUTION_PENDING` | 実装/計画あり、対象分母の完走なし |
| `BLOCKED` | dependency/license/runner/policy/artifactで停止 |
| `NOT CERTIFIED` | 成功証拠なし、fail-closed |

### Inventory / planner denominators

```text
Broad v1                           = 174
Probabilistic effective v1         = 76
Combined Unified accounting        = 250
Combined Unified × six games       = 1,500
Current `loto3 campaign` planner   = Broad 174 × 6 = 1,044
```

古い資料のprobabilistic=72はcurrent effective countではありません。一方、**250/1,500は現在の単一`loto3 campaign`コマンドの実行分母ではありません**。current plannerはBroad catalogのみを対象にします。Probabilisticは別surfaceです。

---

## 2. Broad v1 = 174

Broad v1は凍結された科学比較分母です。dynamic/Expanded inventoryを足し戻しません。

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

- Probabilistic effective: **76**
- Combined Unified accounting: **250**
- current Broad campaign plan: **1,044 = 174 × 6**
- scikit-learn dynamic: installed-version dependent
- sktime registry: current isolated lane 141 discovered/importable
- Expanded v2: Phase 1=210、final count未freeze
- TSL / BasicTS / Merlion等の追加inventory

---

## 3. 主要ライブラリ / 実行面

| Library | Inventory | Execution surface | GPU/runtime evidence | OOF |
|---|---:|---|---|---|
| sklearn Broad | 7 | shared/Broad campaign | tree-specific | 未完 |
| sklearn dynamic | version-dependent | `loto-sklearn` | provider/certify surface | 未完 |
| XGBoost | 1 | resource-aware Broad campaign | CUDA exact-head VERIFIED | 未完 |
| CatBoost | 1 | resource-aware Broad campaign | GPU exact-head VERIFIED | 未完 |
| LightGBM | 2 | resource-aware Broad campaign | OpenCL GPU VERIFIED / CUDA learner unavailable | 未完 |
| StatsForecast | 41 | shared 8 + campaign | lifecycle + real-game development | 部分実行 |
| MLForecast | Auto 8 | direct 2 + Auto | backend dependent | 未完 |
| NeuralForecast fixed | 37 | shared subset + dedicated | GPU capable | 未完 |
| NeuralForecast Auto | 36 | AutoModel runner | Ray/Optuna/GPU | 未完 |
| AutoGluon | Broad 1 / Expanded 37 | isolated | backend dependent | 未完 |
| Darts | Broad 1 / 58 public exports | provider/campaign | local NLinear/DLinear GPU verified, main pending | 未完 |
| GluonTS | Broad 1 / isolated lanes | shared + provider | Draft #309 18/18 CPU lifecycle | 未完 |
| sktime | Broad 1 / registry 141 | isolated | fixed P1 4 formal PASS | 未完 |
| skforecast | Broad 1 | repository integration pending | operator-local partial runtime | 未完 |
| TSFM | 21 | provider-specific | retained 19/21 certified | 未完 |
| probabilistic | effective 76 | separate catalog/run/API surface | backend-specific | combined planner未実装 |

Detailed identities and arguments: [`docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`](docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md).

---

## 4. skforecast operator-local evidence

PR #310 added [`docs/SKFORECAST_RUNTIME_CERTIFICATION.md`](docs/SKFORECAST_RUNTIME_CERTIFICATION.md). Evidence is explicitly **operator-local**, source head `9fcc127...`, not current-main certification.

Highlights:

- core recursive/direct/multi-series/multivariate surfaces PASS;
- features/backtesting/Optuna/persistence/drift/intervals PASS;
- `ForecasterRnn` LSTM/GRU GPU VERIFIED and LSTM CPU fallback VERIFIED;
- Chronos-2 GPU/CPU PASS;
- TimesFM 2.5 GPU/CPU PASS;
- Moirai-2 runtime only under unsupported dependency override; normal routability BLOCKED;
- TabICL v2 runtime + checkpoint SHA-256 VERIFIED;
- TabPFN-TS v3 inference blocked before weights by invalid/expired Prior Labs token/license gate.

Do not convert this evidence into current-main Expanded v2 completion or six-game OOF.

---

## 5. Darts local-only evidence

Current main has Darts 0.46.1 discovery/provider/campaign/runtime bootstrap foundation. Separately, a local exact-worktree verified:

```text
darts=0.46.1
torch=2.9.1+cu130
CUDA=13.0
pytorch-lightning=2.6.5
GPU=RTX 5070 Ti
official bootstrap=PASS
campaign_execution_allowed=true
NLinear actual GPU fit/predict=VERIFIED
DLinear actual GPU fit/predict=VERIFIED
```

This dependency/profile/lock correction is not merged. Current main `smoke_models` is not wired to actual construct/fit/predict. The first proposed smoke-harness patch failed with `corrupt patch at line 381`; formal smoke integration remains **EXECUTION_PENDING**. See [`docs/darts/CURRENT_STATE_DARTS.md`](docs/darts/CURRENT_STATE_DARTS.md).

---

## 6. 2026-08-12〜13 key merges / open boundary

| PR | SHA / head | Scope |
|---|---|---|
| #268 | `81bd4f81...` | statistical/causal foundation |
| #270/#277 | merged | resource-aware runner + scheduler stabilization |
| #273/#274/#276 | merged | repository observability/control-center/dashboard |
| #293 | `f04cd876...` | Expanded v2 foundation + AutoGluon 37 |
| #295/#296 | merged | Toto2 family + 22M runtime infrastructure |
| #301 | `3cc73dba...` | dynamic sklearn provider |
| #302 | `7d75dadc...` | parallel Broad campaign orchestration |
| #303 | `b9be4174...` | isotonic route |
| #304 | `de1444af...` | XGBoost/CatBoost GPU routing |
| #305 | `a03053ea...` | LightGBM accelerator probe |
| #306 | `feb4ea5e...` | LightGBM OpenCL GPU routing |
| #307 | `ed7d6c81...` | sktime P1 normalization |
| #308 | `932977f7...` | README reconciliation |
| #310 | `4f4f8579...` | current state + skforecast operator evidence |
| #312 | `063120fd...` | library/model matrix current-evidence alignment |
| #311 | `9623f2a5...` | Darts evidence + Broad planner boundary documentation alignment |
| #309 | Draft `edba730a...` | GluonTS P6/P7 CPU lifecycle repair; main pending |

---

## 7. Scientific contract

Primary metric: **Hit@±1**.

Also report MAE, MSE, RMSE, position Hit@±1, all-position Hit@±1. Baselines include Random, fixed, mean, median, last/recent, frequency and statistical models.

```text
Train-only preprocessing/HPO
-> chronological Validation/OOF
-> all seeds + mean/variance/worst
-> prediction SHA-256 seal before actual
-> explicit Holdout authorization
-> Holdout
-> sealed Prospective
-> actual arrival/scoring
-> human promotion
```

Holdout=CLOSED. Prospective=CLOSED. Automatic promotion=FORBIDDEN.

---

## 8. Common commands

```bash
uv run loto3 games
uv run loto3 catalog --counts
uv run loto models list

# Broad v1 plan only: 174 × 6 = 1,044
uv run loto3 campaign --output unused --plan-only

# separate probabilistic surface: effective catalog 76
uv run loto3 probabilistic catalog-list

uv run loto-sklearn list
uv run python -m loto.evaluation.parallel_campaign --help
ROOT="$PWD" SKTIME_NO_PAUSE=1 bash scripts/run_sktime_p1_matrix_certification.sh
uv run loto neuralforecast automodel-run --help
uv run loto data acquire --help
```

Darts runtime foundation:

```bash
uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_notorch.yaml \
  --repository-root .

uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_torch.yaml \
  --repository-root .
```

---

## 9. Source of truth

1. current code/configuration;
2. tests/workflows/repository-retained evidence;
3. exact-source operator/local evidence with provenance;
4. merged PR/commit history;
5. live GitHub Issues / Linear state;
6. current documentation;
7. historical snapshots.

異なるSHAの成功証拠を「current mainで同一条件 VERIFIED」と混ぜません。
