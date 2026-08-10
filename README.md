# Loto Forecast Platform

6ゲーム（ミニロト / ロト6 / ロト7 / ビンゴ5 / ナンバーズ3 / ナンバーズ4）を対象に、統計・機械学習・深層学習・時系列基盤モデルを **同一のleakage-safe評価条件で比較する研究＋運用基盤** です。

Package versionはREADMEへ手書きしません。canonical versionは`loto.version.__version__`、installed CLI、またはpackage metadataから確認してください。

## 最初に読む資料

- [`docs/STATUS.md`](docs/STATUS.md) — GitHub/Linear/科学進捗を突合した **時点付き監査スナップショット**
- [`docs/README.md`](docs/README.md) — live design / generated inventory / historical evidenceの読み分け
- [`docs/DOCUMENTATION_POLICY.md`](docs/DOCUMENTATION_POLICY.md) — stale/current/historical資料の更新規約
- [`docs/MODEL_INVENTORY.md`](docs/MODEL_INVENTORY.md) — 自動生成モデル在庫。`loto3 catalog --counts`が正本
- [`docs/evaluation_protocol/PROTOCOL_V2.md`](docs/evaluation_protocol/PROTOCOL_V2.md) — formal評価protocol

固定されたActions run ID、PR状態、main SHA、PCのOS可否などは時間とともに変わります。READMEではそれらを恒久的な「current値」として扱いません。

## Audited project state — 2026-08-10 16:24 JST

この節は監査時点のスナップショットです。live値は[`docs/STATUS.md`](docs/STATUS.md)に記載した再取得方法で確認してください。

```text
AUDIT_BASE_MAIN=0bb4680b2d26cfd32788381f580d86a4acd0fb6d
PR_240_STATE_AT_AUDIT=merged
PR_240_MERGE_SHA=0bb4680b2d26cfd32788381f580d86a4acd0fb6d
OPEN_PRS_AT_AUDIT=#245 only
OPEN_GITHUB_ISSUES_AT_AUDIT=#239,#118
SCIENTIFIC_PROGRESS_FROM_PR_240=18%
FORMAL_TIMER_OOF_RUN=false
TIMER_INFERENCE_RUN=false
HOLDOUT_OPENED=false
PROSPECTIVE_OPENED=false
ACCURACY_CLAIM=false
CHAMPION_CLAIM=false
PROMOTION=false
```

PR #240でTimer Base 84M leakage-safe OOFの**engineering foundation**は`main`へ統合済みです。ただしformal OOF、Timer inference、Holdout、Prospective、accuracy/champion/promotionは未完了です。

Linux/Windows/WSLの「今この端末で使えるか」はセッション固有です。リポジトリの恒久属性ではありません。リポジトリにはself-hosted Linux standard CIとnative Windows portabilityの検証履歴があり、formal runでは実際に使用するhostのresource/package identityを毎回測定・固定します。

## 5分で確認する

`uv`ベースの基本コマンドはWindows/Linuxで共通です。

```text
uv --version
uv sync --extra dev
uv run loto3 games
uv run loto3 catalog --counts
uv run loto3 catalog --unpinned
uv run loto3 integrity check
```

GitHubのlive repository stateは、maintainer環境では例えば次で再取得できます。

```text
gh pr list -R arumajirou/loto_forecast_platform --state open
gh issue list -R arumajirou/loto_forecast_platform --state open
gh run list -R arumajirou/loto_forecast_platform --limit 20
```

## Installation tiers

正確な依存契約は[`pyproject.toml`](pyproject.toml)と`uv.lock`が正本です。2026-08-10監査時点ではPythonは`>=3.11,<3.14`です。

| install | 主な用途 |
|---|---|
| `uv sync` | core / NeuralForecast / Torch / Transformers |
| `uv sync --extra dev` | pytest / Ruff / mypy / Hypothesis / Optuna / telemetry |
| `uv sync --extra auto-campaign` | Optuna / StatsForecast / resource inspection |
| `uv sync --extra api` | FastAPI / Uvicorn API lane |
| `uv sync --extra postgres` | PostgreSQL data source |
| `uv sync --extra mlflow` | MLflow tracking |
| `uv sync --extra frameworks` | Darts / GluonTS / Lightning / sktime / skforecast / ReservoirPy |
| `uv sync --extra tsfm` | Transformers / Accelerate / Chronos forecasting |
| `uv sync --extra full` | broad research/development dependency set incl. boosting / Nixtla / Ray / telemetry |

Formal runtime certificationでは「依存がlockにある」ことと「対象hostでload/inferenceが成功した」ことを分離します。

## Model inventory

モデル件数は[`docs/MODEL_INVENTORY.md`](docs/MODEL_INVENTORY.md)を経由し、最終的には`loto3 catalog --counts`を正とします。

2026-08-10監査スナップショット:

| library | registered count | role |
|---|---:|---|
| builtin | 4 | mandatory/simple controls |
| sklearn | 7 | candidate / position ML baselines |
| lightgbm | 2 | boosting candidate / position |
| xgboost | 1 | candidate boosting |
| catboost | 1 | candidate boosting |
| statsforecast | 41 | statistical `position_series` forecasting |
| neuralforecast | 37 | fixed neural `position_series` models |
| neuralforecast_auto | 36 | HPO-enabled NeuralForecast AutoModels |
| mlforecast_auto | 8 | lag/exogenous MLForecast Auto models |
| hierarchicalforecast | 10 | reconciliation methods |
| tsfm | 21 | pretrained/foundation models |
| autogluon | 1 | AutoML provider entry |
| darts | 1 | ensemble framework entry |
| gluonts | 1 | probabilistic framework entry |
| sktime | 1 | ensemble framework entry |
| skforecast | 1 | recursive forecasting framework entry |
| reservoirpy | 1 | ESN/reservoir entry |
| **total** | **174** | generated catalog total |

### Task semantics

| task | meaning |
|---|---|
| `candidate` | 各候補番号のprobability/ranking |
| `position` | 各抽選位置を直接回帰 |
| `position_series` | 各位置を時系列としてforecast |
| `foundation` | pretrained TSFMへcontextを与えてforecast |
| `reconciliation` | 既存forecastを階層制約へ整合 |

### Major model families

- **NeuralForecast fixed (37):** RNN/GRU/LSTM/TCN/DeepAR/NHITS/NBEATS/NBEATSx/TFT/PatchTST/iTransformer/xLSTM/XLinearなど。
- **NeuralForecast Auto (36):** AutoRNN/AutoLSTM/AutoGRU/AutoNHITS/AutoTFT/AutoPatchTST/AutoTimeXer/AutoXLinearなど。search backendはruntime契約として検証します。
- **StatsForecast (41):** AutoARIMA/AutoETS/SeasonalNaive/HistoricAverage/Croston系/Theta系/TBATS/MSTLなど。mandatory statistical baseline群を含みます。
- **MLForecast Auto (8):** LightGBM/XGBoost/CatBoost/linear/Ridge/Lasso/ElasticNet/RandomForest。
- **HierarchicalForecast (10):** BottomUp/TopDown/MiddleOut/MinTrace/OptimalCombination/ERM等。予測器ではなくreconciliation層です。
- **TSFM (21):** Chronos, TimesFM, Moirai, TiRex, Toto, TTM, Lag-Llama等。登録とrevision/runtime certificationは別です。

TSFM revision未固定状態は捏造SHAで埋めず`UNPINNED`として扱います。formal protocolへ入れる前にrepo/revision/artifact hash/license/package/runtime identityを固定します。

## “利用可能”を7段階に分ける

```text
1. Registered
2. Dependency available
3. Runtime loadable
4. Inference verified
5. OOF evaluated
6. Holdout eligible/evaluated
7. Promotion eligible/promoted
```

**Level 1だけを見てruntime/accuracy successとは記載しません。**

Runtime certificationでは最低限、model/revision、load、input、inference、output shape、finite values、effective device、GPU PID/VRAM、CPU fallback、アンロード後のresource解放を実測します。

## Scientific acceptance policy

Primary KPIは`Hit@±1`です。formal比較では併せて以下を保存します。

```text
hit_at_1
position_hit_at_1
all_positions_hit_at_1
mae
mse
rmse
```

最低限のbaseline:

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

評価規則:

- Train / Validation / Holdout / Prospectiveを時間順で分離する。
- Scaler、Encoder、特徴量選択、HPO/チューニングはTrain内だけでfitする。
- OOFは複数seedを全て保持し、mean / population variance / worst value / worst seedを保存する。
- best-seed-only採用は禁止する。
- 予測値はtarget actual参照前にimmutable write + SHA-256 + timestampで固定する。
- 異なる`protocol_hash`の結果を黙って同一leaderboardへ混ぜない。
- Hit@±1が劣るcandidateをMAEだけで上位採用しない。
- valid outcomeとして`NO_MODEL_BEATS_BASELINE` / `champion=null`を認める。

## Evaluation Protocol v2

[`docs/evaluation_protocol/PROTOCOL_V2.md`](docs/evaluation_protocol/PROTOCOL_V2.md)はOS固有のprotocolではありません。formal runのhostがWindowsでもLinuxでも、**そのrunで実測した**code/data/resource/package identityを固定します。別hostの過去値をコピーして再現性を装いません。

Timer Base 84Mの正式科学作業はGitHub Issue #239 / Linear TAJ-12で追跡しています。PR #240 mergeはIssue #239の科学完了を意味しません。

## Data contract

Raw dataは上書きせず不変の正本として扱います。formal campaignでは少なくとも次を証拠化します。

1. source identity;
2. immutable data snapshot + SHA-256;
3. chronological split manifest + SHA-256;
4. duplicate / missing / ordering / domain / future-information audit;
5. feature availability boundary;
6. prediction-before-actual ordering;
7. Holdout/Prospectiveの未開封状態または明示的な後段開封記録。

SQLite/PostgreSQL/API接続が成功しただけではformal dataset確定にはなりません。

## Experiment tracking and evidence

Formal Run IDには設定、data hash、code hash、Git commit、model/revision、seed、予測、実測、評価値、ログ、resource/GPU情報を結びます。既存のMLflow/PostgreSQL/DuckDB/Parquet等の契約を優先し、互換性のない並行tracking形式を増やしません。

Evidenceは可能な限り次を保持します。

- protocol/data/split/feature/model/runtime manifests;
- SHA-256 inventory;
- stdout/stderr/exit code/timestamps;
- per-fold/per-seed predictions and metrics;
- baseline comparison;
- runtime certification;
- independent verification report.

## Repository design sources

- [`specs/001-full-coverage/spec.md`](specs/001-full-coverage/spec.md)
- [`specs/001-full-coverage/plan.md`](specs/001-full-coverage/plan.md)
- [`specs/001-full-coverage/research.md`](specs/001-full-coverage/research.md)
- [`specs/001-full-coverage/tasks.md`](specs/001-full-coverage/tasks.md)
- [`.specify/memory/constitution.md`](.specify/memory/constitution.md)

## Historical reports are not deleted

古い`VERIFICATION_REPORT`、`HANDOFF`、CI run ID、SHA256SUMSは「古いから誤り」なのではなく、**その時点のevidence**です。問題はそれをlive stateと読んでしまうことです。

そのため本リポジトリでは、履歴資料を消去・改竄する代わりに[`docs/DOCUMENTATION_POLICY.md`](docs/DOCUMENTATION_POLICY.md)で分類し、[`docs/STATUS.md`](docs/STATUS.md)から現在の監査スナップショットへ誘導します。

## Theoretical bounds

[`docs/THEORETICAL_BOUNDS.md`](docs/THEORETICAL_BOUNDS.md)を参照してください。MAE下限とHit@±1上限は別目的であり、同時最適化できない場合があります。formal selection priorityはHit@±1を先に固定します。

## License / research disclaimer

本ソフトウェアは時系列予測手法の研究を目的とします。宝くじの当選を予測する能力は主張しません。正式な性能主張は、固定済みprotocol、リーク検査、baseline比較、multi-seed集約、prediction sealing、必要なruntime evidenceを通過した実測結果だけを根拠にします。
