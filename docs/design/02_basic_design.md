# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. アーキテクチャ方針

採用方式は「契約駆動モジュラーモノリス + 隔離Model Worker + Plugin Registry」である。データ契約・評価契約・台帳は単一正本に保ち、依存競合が大きいモデル群は別OCI/uv環境で実行する。

```text
Browser / CLI / Scheduler
        |
API Gateway + RBAC
        |
Experiment Orchestrator ---- Approval / Release Service
        |
        +-- Data Pipeline
        +-- Feature Pipeline
        +-- Evaluation Harness
        +-- Decoder / Calibration / Ensemble
        +-- Model Gateway ---- Worker Pool
        |                       |-- nixtla-worker
        |                       |-- classical-ml-worker
        |                       |-- autogluon-worker
        |                       |-- darts-worker
        |                       |-- gluonts-worker
        |                       |-- hf-tsfm-worker
        +-- Registry / Artifact Store / MLflow
        +-- OpenTelemetry / Prometheus / Loki
```

## 2. 論理コンポーネント

| コンポーネント | 責務 |
|---|---|
| Data Acquisition | HTTP/ローカル取得、Raw保存、取得証跡 |
| Normalizer | 文字コード、列名、型、ゲーム別Canonical化 |
| Feature Builder | draw/candidate/position/exogenous特徴量、As-of検査 |
| Dataset Factory | モデル別long/wide/indicator/position形式へ変換 |
| Model Registry | モデルID、library、revision、license、capability管理 |
| Model Gateway | 共通RPC、timeout、retry、worker routing |
| Worker | モデル固有依存でfit/predict/save/loadを実行 |
| Search Controller | Optuna study、Ray resource scheduling、pruning |
| Evaluation Harness | Nested Rolling CV、Holdout、seed、統計比較 |
| Calibration Service | Platt、Temperature、Isotonic、Conformal |
| Residual Service | OOF残差補正、bias/drift補正 |
| Ensemble Service | 非負重み、stacking、shrinkage |
| Decoder | DP/beam/rerank、組合せ制約 |
| Promotion Service | Gate、Pareto、承認、Champion切替 |
| Observability | logs/traces/metrics/profiles/GPU evidence |
| Web UI | データ・実験・比較・監査・運用画面 |

## 3. 配備構成

| 環境 | 用途 | 特徴 |
|---|---|---|
| Windows local | データ確認、CLI、smoke、UI | CPU中心、Docker不要でも動作 |
| Linux development | 実装・小規模GPU試験 | uv環境、SQLite/ローカルMLflow |
| Linux validation | 正式CV、複数Worker | OCI、PostgreSQL、MinIO、Ray |
| Linux production | 定期再学習・封印・Shadow | systemd/Kubernetes選択、署名Bundleのみ |

## 4. データフロー

```text
Source -> Raw -> Validated -> Canonical -> Feature Snapshot
       -> Dataset View -> Trial Prediction -> OOF Prediction
       -> Calibration/Residual -> Ensemble -> Legal Decode
       -> Evaluation -> Promotion -> Sealed Forecast -> Shadow Score
```

各段階はmanifestとSHA-256を持つ。上流Artifact変更時は下流を無効化し、同一hashなら再利用する。

## 5. モデル実行方式

### 5.1 Worker分類

| Worker | 主なライブラリ | 実行資源 |
|---|---|---|
| stats-worker | StatsForecast | CPU、多プロセス |
| ml-worker | MLForecast、LightGBM、XGBoost、CatBoost、sklearn | CPU/GPU選択 |
| neural-worker | NeuralForecast | CUDA GPU |
| hierarchy-worker | HierarchicalForecast | CPU中心 |
| autogluon-worker | AutoGluon TimeSeries/Tabular | CPU/GPU、大容量環境 |
| darts-worker | Darts、PyTorch、TiRex、TimesFM | GPU、モデル別extra |
| gluonts-worker | GluonTS、DeepAR、確率モデル | CPU/GPU |
| hf-worker | Chronos、TTM、Moirai等 | GPU/CPU、revision固定 |
| custom-worker | ESN、TabPFN、独自モデル | 個別環境 |

### 5.2 共通モデル契約

- `validate_request()`
- `prepare_dataset()`
- `fit()`
- `predict()`
- `predict_proba_or_quantiles()`
- `save()` / `load()`
- `get_capabilities()`
- `get_resource_requirements()`
- `get_provenance()`
- `healthcheck()`

## 6. 評価アーキテクチャ

```text
Historical data
  |- fixed holdout: latest 50 historical draws (sealed)
  `- development region
       `- outer rolling folds
            `- inner rolling folds
                 |- feature selection
                 |- hyperparameter search
                 |- calibration selection
                 `- ensemble weights
```

- h=1
- expanding/rolling windowを設定可能
- gap/embargoを設定可能
- outer foldの予測のみモデル比較へ使用
- candidateが曖昧ならseed 5、正式認定はseed 10

## 7. UI基本構成

| 画面 | 内容 |
|---|---|
| Overview | 次回抽選、最新封印、Champion、SLO、アラート |
| Data | Raw/Canonical差分、品質、取得元、As-of状態 |
| Feature Lab | 特徴量定義、利用可能時刻、重要度、分布 |
| Model Catalog | モデル、version、license、capability、資源 |
| Experiment Builder | dataset/fold/model/search/seed/予算定義 |
| Live Runs | Stage、trial、GPU、ログ、trace、停止/再開 |
| Leaderboard | Hits/±1/MAE/校正/速度/VRAM、Pareto |
| Forecast | 組合せ、候補確率、位置分布、署名 |
| Shadow | 実測採点、累積e-process、drift |
| Operations | Worker、queue、disk、DB、backup、restore |
| Approvals | Holdout開封、Champion、Release承認 |

## 8. 観測設計

- Logs: structlog JSON -> Loki
- Traces: OpenTelemetry -> Tempo/Jaeger
- Metrics: Prometheus -> Grafana
- Experiments: MLflow
- Search: Optuna Dashboard / Ray Dashboard
- GPU: DCGM exporterまたはnvidia-smi collector
- Profiles: PyTorch Profiler、py-spy、memrayを研究実行で利用

相関キーは`release_id/run_id/trial_id/fold_id/seed/model_id/worker_id`。
