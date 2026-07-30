# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. API原則

- `/api/v2`
- OpenAPI 3.1
- Bearer/OIDC認証
- Idempotency-Key対応
- 長時間処理は非同期Job
- 全応答に`request_id`、操作対象に`run_id`等を付与

## 2. 主要API

| Method | Path | 権限 | 概要 |
|---|---|---|---|
| POST | `/data/acquisitions` | Operator | データ取得開始 |
| GET | `/datasets` | Viewer | データ版一覧 |
| POST | `/features/builds` | Researcher | 特徴量生成 |
| GET | `/models` | Viewer | モデルレジストリ |
| POST | `/models/discover` | Administrator | GitHub/HF候補収集 |
| POST | `/experiments` | Researcher | 実験作成 |
| POST | `/experiments/{id}/start` | Researcher | 実験開始 |
| POST | `/experiments/{id}/cancel` | Operator | 中断 |
| GET | `/experiments/{id}/leaderboard` | Viewer | 比較結果 |
| GET | `/trials/{id}/resources` | Viewer | GPU/CPU証跡 |
| POST | `/holdouts/{id}/open-request` | Researcher | Holdout開封申請 |
| POST | `/promotions` | Approver | 昇格判断 |
| POST | `/forecasts/seal` | Operator | 次回予測封印 |
| POST | `/shadow-scores` | Operator | 実測採点 |
| GET | `/metrics` | Viewer | Prometheus |

## 3. 実験作成例

```json
{
  "lottery":"loto7",
  "horizon":1,
  "tasks":["candidate","position"],
  "model_set":"p0-formal",
  "outer_cv":{"folds":10,"test_size":1},
  "inner_cv":{"folds":5,"test_size":1},
  "seeds":{"search":1,"outer":3,"certification":10},
  "budget":{"max_trials":200,"max_gpu_hours":24},
  "objectives":["hits_at_7","mean_within_1"],
  "gates":{"calibration_relative":0.02,"max_model_weight":0.60}
}
```

## 4. エラー契約

| code | 意味 |
|---|---|
| DATA_CONTRACT_VIOLATION | Canonical/As-of違反 |
| MODEL_NOT_COMPATIBLE | task/OS/資源非対応 |
| RESOURCE_UNAVAILABLE | GPU/VRAM/worker不足 |
| TRIAL_DISQUALIFIED | 証跡・リーク・違法出力 |
| HOLDOUT_LOCKED | 承認前アクセス |
| RELEASE_NOT_APPROVED | 未署名Bundle |
| ARTIFACT_INTEGRITY_ERROR | hash不一致 |
