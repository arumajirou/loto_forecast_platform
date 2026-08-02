# 詳細設計書

## 主要モジュール

- `loto_ops.db`: DB接続、初期化、COPY投入、スキーマ確認
- `loto_ops.pipeline`: 既存プロジェクト呼び出し、exog/unified生成、全体オーケストレーション
- `loto_ops.quality`: 品質検査、テーブルプロファイル、HTML/JSONレポート
- `loto_ops.artifacts`: manifest、lineage、light/full ZIP作成
- `loto_ops.webapp`: Streamlit運用作業台

## データモデル

- `RunManifest`: 実行全体の履歴
- `StageResult`: 各ステージの成功/失敗/行数/列数
- `TableProfile`: テーブルの件数、列数、日付範囲、欠損、重複
- `ArtifactInfo`: 成果物パス、サイズ、SHA256

## 例外処理

危険操作、DB接続失敗、空データ、exog未作成、品質ゲート失敗を明示的に失敗扱いにする。
