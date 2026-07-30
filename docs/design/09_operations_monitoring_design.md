# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. 運用周期

| 周期 | 処理 |
|---|---|
| 抽選後 | データ取得、品質検査、Shadow採点 |
| 毎抽選 | Champion再学習、校正、封印 |
| 週次 | 軽量候補再探索、依存脆弱性確認 |
| 月次 | 大規模モデル再探索、復旧試験 |
| 四半期 | モデルカタログ再調査、廃止判断 |

## 2. SLO

- データ取得・検証 15分
- 特徴量 20分
- Champion再学習 90分
- 校正/decoder 30分
- verify/seal/register 20分
- 総計3時間、80%でWarning

## 3. アラート

| Severity | 例 | 自動処理 |
|---|---|---|
| Critical | 封印失敗、データリーク、hash不一致 | 停止、旧Champion使用 |
| Warning | SLO80%、VRAM逼迫、校正悪化 | retry/縮退、通知 |
| Info | 実験完了、Shadow採点 | 記録のみ |

## 4. バックアップ

日次増分、週次完全、月次オフライン。四半期ごとに別ホストへリストアし、RPO/RTOを測定する。封印予測、Release、監査、メタデータは自動削除しない。

## 5. 実行効率

- P0 CPUモデルを先行し、弱いDL trialを早期除外
- feature/dataset cacheを共有
- GPUモデルはVRAM予約、同一TSFMは常駐server
- failed temp artifactから容量回収
- Ray placement groupでGPU/CPU資源を固定
