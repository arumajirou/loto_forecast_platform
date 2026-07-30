# 要件定義書

## 1. 目的

Loto7を参照実装とし、他の数字選択式くじへ拡張できる共通予測研究・運用基盤を構築する。目的は、厳密な検証を通過した範囲で集合的中性能を最大化することであり、見かけ上の最良値を作ることではない。

## 2. 成功指標

- 主指標: 平均Hits@7
- 副指標: 位置別±1率、位置MAE/MSE、NDCG@7
- 安全指標: Brier Score、Log Loss、ECE
- 暫定改善: Champion比 +0.10 Hits@7
- 正式改善: Champion比 +0.15 Hits@7
- 校正非劣性: Brier/Log Loss相対+2%以内、ECE絶対+0.02以内

## 3. 評価契約

- Nested Rolling CV
- 未使用の過去固定Holdout 50抽選
- 将来Shadow最低20抽選、正式判定50抽選
- fold過半数勝利、抽選単位bootstrap、multi-seed
- 証拠不足は棄却ではなく継続評価
- 多重比較は探索ファミリー台帳、段階選抜、FDR、Holdout進出数制限で管理

## 4. データ要件

- raw / validated / canonical / featuresの不変層
- SHA-256、取得元、取得時刻、Git commit、スキーマ版を保存
- 抽選マスター、位置表、37候補表、外生変数表
- `event_time`, `available_at`, `ingested_at`, `forecast_created_at`, `draw_time`
- 原則 `available_at <= forecast_created_at < draw_time`
- 外生変数はknown_future / historical_only / static / prohibitedに分類
- 公式正本と独立第二取得元を照合し、不一致はquarantine

## 5. モデル要件

- 集合二値分類 + ランキング
- 共有エンコーダ + 7位置ヘッド + 合法範囲マスク
- 独立モデルを基準とし、部分共有マルチタスクは昇格候補
- DP候補生成 + 組全体再ランキング
- OOF校正・OOF残差補正
- 一様、理論、頻度、統計、機械学習を常時ベースライン化
- NeuralForecast・基盤モデルは研究隔離トラック

## 6. 運用要件

- Linuxが本番正本、Windows/WSLは補助
- 新抽選ごとに固定Championを再学習、10回ごと等に再探索
- 正式基準はゼロから再学習、ウォームスタートは並走候補
- 本番SLO 3時間
- 予測を抽選前に署名・封印し、後から上書きしない
- GPU指定trialはモデル・batch・PID・VRAM証跡が揃わなければ失格
- MLflow、台帳、Artifact、Prometheus/Grafana、JSONLログを共通IDで接続

## 7. セキュリティ

- RBAC: Viewer / Researcher / Operator / Approver / Administrator
- Champion昇格と封印取消は二段階承認
- Secretsは環境変数またはSecret Storeで管理し、ログ・MLflowへ平文保存しない
- 危険操作はdry-run、再確認、監査記録

## 8. 初期受入

Trusted Vertical Sliceが、データ取得相当のCSV入力から、検証、特徴量、軽量モデル、デコード、評価、封印、台帳、Release Bundleまで一回のコマンドで完了し、全自動テストを通過すること。
