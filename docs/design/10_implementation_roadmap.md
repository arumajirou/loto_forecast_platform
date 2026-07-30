# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. 実装フェーズ

| Phase | 成果 | 完了条件 |
|---|---|---|
| 0 | v1.1.0監査・契約固定 | gap matrix承認 |
| 1 | Model Registry/Adapter/Worker基盤 | dummy+Stats+ML Adapter PASS |
| 2 | 正式Evaluation Harness | Nested CV、±1詳細、Leaderboard |
| 3 | Nixtla統合 | 4ライブラリP0モデル完走 |
| 4 | Optuna/Ray/GPU証跡 | trial並列、資源証跡、resume |
| 5 | Calibration/Residual/Ensemble | OOF契約PASS |
| 6 | TSFM/HF Worker | Chronos/TTM/TiRex/TimesFM比較 |
| 7 | UI/Observability | 全画面、MLflow/Grafana/Trace連携 |
| 8 | Holdout/Shadow/Promotion | 受入・Release Bundle |
| 9 | 他くじPlugin | Loto6/Mini/Numbers/Bingo予測 |

## 2. 実装優先順位

P0は「モデル数」より「公平な比較契約」を優先する。最初の正式版はUniform/Frequency/Theory/StatsForecast/MLForecast/DLinear/NHITS/TiDE/TCN/GRU/ESNで閉じる。その後TSFMを追加する。

## 3. 成果物

- 実装コード、uv.lock、OCI images
- OpenAPI/AsyncAPI/JSON Schema
- Model Catalog、Leaderboard、Pareto report
- Grafana dashboard、Runbook
- テスト証跡、SBOM、署名Release Bundle
