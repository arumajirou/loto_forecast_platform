# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. テスト戦略

| 層 | 内容 |
|---|---|
| Unit | 数式、特徴量、指標、decoder、設定、型 |
| Property | 合法組合せ、確率範囲、時間順序、冪等性 |
| Contract | Adapter、API、イベント、Artifact schema |
| Integration | 各Worker実fit/predict、DB、MLflow、Ray |
| Differential | 旧系・他ライブラリ・理論実装との比較 |
| Statistical | seed/fold安定性、bootstrap、e-process |
| Performance | throughput、SLO、VRAM、disk、queue |
| Resilience | OOM、worker kill、DB断、disk full、resume |
| Security | RBAC、自己承認、Secret漏洩、artifact改ざん |
| Acceptance | Rawから封印・Shadowまで |

## 2. 必須テストケース

- 各P0モデルが最低1 foldで実fit/predict
- save/load後に許容誤差内で同一予測
- future列を混入するとリーク検査が失敗
- Holdout URIへ未承認アクセスすると403
- GPUモデルがCPU fallbackしたら失格
- Worker kill後にtrialをretryし重複登録しない
- 同一設定・seed・Bundleで予測再現
- ±1の位置別/平均/全位置成功率が手計算一致
- Ensemble重み制約が常に成立
- 封印後にforecast.jsonを変更すると検証失敗

## 3. 品質Gate

- unit/contract 100% PASS
- P0 Adapter integration 100% PASS
- Critical mutation score対象で閾値達成
- E2E SLO内
- 警告はownerと期限を付与
