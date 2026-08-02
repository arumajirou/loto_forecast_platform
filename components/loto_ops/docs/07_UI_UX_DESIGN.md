# UI/UX設計書

## コンセプト

pgAdmin4代替ではなく、データ作成・検証・提出の作業台として設計する。

## 画面

- Overview: DB・データセット・exog・ZIP状態を3秒で把握
- Pipeline Run: ステップ別実行とログ表示
- Data Browser: スキーマ、テーブル、カラム、プレビュー
- Quality: 品質スコア、欠損、重複、日付範囲
- Artifacts: CSV/Parquet/SQLite/ZIP/manifest確認
- Scheduler: systemd timer状態とコマンド表示
- Settings: DB接続、パス、exogバグ診断

## 状態色

- 緑: 成功
- 黄: 警告
- 赤: 失敗
- 灰: 未実行
- 青: 実行中
