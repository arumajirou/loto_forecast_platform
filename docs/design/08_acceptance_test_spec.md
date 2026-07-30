# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. 受入シナリオ

### AT-001 多モデル比較

Given Canonical Loto7の開発領域が存在する
When P0正式モデルセットをNested Rolling CVで実行する
Then 全モデルのouter予測、±1、Hits、校正、時間、資源がLeaderboardへ出力される

### AT-002 ±1 Champion

Given 全outer foldが完了している
When `champion_within1`を選抜する
Then mean_within_1が最大で、worst_position Gate、校正Gate、再現性Gateを通過したモデルが選ばれる

### AT-003 GPU証跡

Given GPU必須モデルを実行する
When trialが完了する
Then PID一致、CUDA device、peak VRAM、utilサンプルが保存される

### AT-004 Holdout隔離

Given モデル設定が未凍結である
When ResearcherがHoldoutへアクセスする
Then拒否され監査イベントが残る

### AT-005 全経路

Given Raw CSVまたは許可済みURL
When正式パイプラインを実行する
Then取得、成型、特徴量、探索、評価、承認、封印、監視が完了する

## 2. 本番切替条件

- P0モデル群の比較が完走
- 固定Holdoutで旧Championに非劣性
- 5回以上のShadowで重大障害なし
- Release Bundle・復旧演習PASS
- 未解決Criticalゼロ
