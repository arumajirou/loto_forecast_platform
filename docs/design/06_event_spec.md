# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. イベント原則

CloudEvents 1.0互換JSONを採用し、Kafka/NATS/Redis Streamsのいずれにも移行可能な抽象化を置く。初期はPostgreSQL Outbox + JSONLで実装する。

## 2. イベント一覧

| Type | Producer | 主要payload |
|---|---|---|
| `data.acquisition.completed` | Data | dataset_id, sha256, rows |
| `data.quality.failed` | Data | rule_id, severity, quarantine_uri |
| `feature.build.completed` | Feature | feature_set_id, asof_report |
| `experiment.created` | Orchestrator | experiment_id, config_hash |
| `trial.started` | Worker | model_id, fold, seed, resources |
| `trial.metric.reported` | Worker | step, metric, value |
| `trial.completed` | Worker | status, artifacts, summary |
| `trial.disqualified` | Evaluator | reason, evidence |
| `gpu.evidence.sampled` | Observer | pid, uuid, util, vram |
| `leaderboard.updated` | Evaluator | top models, pareto |
| `holdout.open.requested` | Approval | requester, reason |
| `model.promotion.requested` | Promotion | candidate, comparison |
| `model.promoted` | Promotion | champion type, release_id |
| `forecast.sealed` | Sealing | forecast_id, signature, timestamp |
| `shadow.scored` | Shadow | actual, metrics, cumulative |
| `alert.raised` | Alerting | severity, runbook |

## 3. 冪等性

各イベントは`event_id`を持ち、consumerは処理済みIDを保存する。Artifact生成イベントは対象hashを含み、同一hashの再処理を安全に無視する。
