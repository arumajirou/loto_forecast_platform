# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）

## 1. 現行差分

| 領域 | v1.1.0 | v2.0目標 | 優先度 |
|---|---|---|---|
| データ取得・成型 | 実装済み | 複数取得元・Quarantine・As-of強化 | P1 |
| 特徴量 | 基本実装 | Registry、外生変数、fold内選択 | P0 |
| モデル比較 | Uniform/Frequency中心 | P0/P1/P2モデルセット | P0 |
| NeuralForecast | Constructor Adapter | fit/CV/predict/save/load完全接続 | P0 |
| StatsForecast | なし | 統計・疎系列Baseline | P0 |
| MLForecast | なし | LightGBM等とOptuna | P0 |
| HierarchicalForecast | なし | 加法階層を実験トラック化 | P2 |
| TSFM | なし | 隔離Worker、revision固定 | P1 |
| 評価 | 単純Rolling | Nested Rolling CV、Holdout | P0 |
| ±1 | 平均指標のみ | 位置別・最悪・全位置・集合割当 | P0 |
| 校正 | identity | OOF校正選択 | P0 |
| 残差・Ensemble | なし | OOF残差、非負重み | P1 |
| GPU証跡 | Run単位 | trial/PID/peak VRAM | P0 |
| 並列化 | 限定 | Ray Resource Broker | P1 |
| UI | FastAPI閲覧中心 | 統合研究・運用UI | P1 |
| Trace | JSONL中心 | OpenTelemetry/Tempo | P1 |
| Model Leaderboard | 2モデルJSON | 全trial/Pareto/資源比較 | P0 |

## 2. P0実装バックログ

1. Model Registryと共通Adapter。
2. StatsForecast/MLForecast/NeuralForecast Worker。
3. Nested Rolling CVと固定Holdout隔離。
4. 詳細±1指標とLeaderboard。
5. Optuna study、trial台帳、失敗分類。
6. trial単位GPU証跡。
7. save/load再現試験。
8. Promotion Gateと用途別Champion。

## 3. 完了定義

- P0モデル群が同一fold・seed・データ版で比較される。
- `model_leaderboard.parquet`、`position_metrics.parquet`、`pareto_front.csv`が生成される。
- 全trialがArtifact、設定、資源証跡へリンクされる。
- 固定Holdoutを未承認で参照できない。
- `champion_hits`と`champion_within1`を独立選抜できる。
