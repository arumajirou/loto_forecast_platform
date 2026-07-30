# 基本設計書（arc42構成）

## 1. はじめにと目標

信頼できる予測評価、将来予測の改ざん防止、モデル交換可能性、他くじへの拡張性を優先する。

## 2. 制約

- 本番正本はLinux単一ホスト
- RTX 5070 Ti 16GBを想定し、GPU深層trialは原則同時1件
- 現在のLoto7履歴は約687抽選であり、複雑モデルの探索過適合を強く警戒
- 多変量系列を正式トラックにせず、単変量/位置別/候補分類と外生変数を分離

## 3. コンテキストとスコープ

外部: 公式抽選情報、第二取得元、MLflow、Prometheus/Grafana、管理者ブラウザ。
内部: data, features, models, calibration, decoding, evaluation, registry, sealing, orchestration, API。

## 4. 解決戦略

- 契約駆動モジュラーモノリス
- Lottery PluginでLoto7固有ルールを隔離
- 全モデルをAdapter化
- 論理契約をPydantic、物理形式をJSON/CSV/Parquetで分離
- 予測とReleaseをハッシュ・署名で不変化

## 5. ビルディングブロック

```text
loto/
├── data             Canonical化・品質検査
├── features         As-of特徴量
├── models           baseline / classification / position / neuralforecast
├── calibration      Platt / Temperature
├── decoding         制約付きDP
├── evaluation       指標・bootstrap・昇格ゲート
├── sealing          予測封印
├── registry         SQLite台帳・Release Bundle
├── observability    Prometheus・GPU証跡
├── orchestration    Trusted Vertical Slice
├── api              FastAPI
└── events           JSONLイベント
```

## 6. ランタイムビュー

```text
INGEST → VALIDATE → CANONICALIZE → BUILD_FEATURES → TRAIN
→ CALIBRATE → DECODE → EVALUATE → SEAL_FORECAST → REGISTER
```

各Stageは台帳とイベントへ追記され、成功済み成果物は不変Artifactとして扱う。

## 7. デプロイビュー

- Linux: Python/uv環境、systemd user service/timer、API、Prometheus
- 認定: OCIコンテナdigest固定
- Windows/WSL: 補助検証、成果物はLinux認定ゲート後のみ採用

## 8. 横断的概念

- 共通ID: run_id, trial_id, model_id, forecast_id, release_id
- 時刻: event_timeとavailable_atを分離
- 再現性: resolved config, environment fingerprint, seed
- 安全: append-only, quarantine, atomic write, rollback record

## 9. アーキテクチャ判断

- ADR-001 Linux本番正本
- ADR-002 Optuna標準/Ray限定
- ADR-003 Hits@7主指標と校正ゲート
- ADR-004 片側e-processは逆棄却に使わない

## 10. 品質要件

再現性、監査可能性、リーク耐性、可用性、3時間SLO、拡張性、最小権限。

## 11. リスク

データ量不足、探索過適合、外部データ公開時刻不明、GPU/ライブラリ数値差、将来Shadow蓄積に時間が必要。

## 12. 用語

Champion: 正式本番モデル。Shadow: 本番出力に使わない将来評価。Release Bundle: 本番構成全体の不変単位。
