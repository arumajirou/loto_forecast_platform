# Loto Forecast Research Platform v2.0 設計書一式

- 文書版: 2.0.0-design
- 作成日: 2026-07-30
- 状態: 再設計版（実装契約）
- 対象: Loto7参照実装、Loto6/Mini Loto/Bingo5/Numbers3/Numbers4拡張
- 本番正本: Linux（Windows/WSLは補助・互換検証）

> 本設計は、既存v1.1.0のデータ取得・成型・特徴量・軽量Baseline・封印・台帳機能を土台に、未達だった多モデル探索、厳密評価、GPU証跡、並列化、UI、ログ・トレース・メトリクスを追加するための再設計である。


## 1. 目的

本システムは、抽選履歴から将来1回先を予測する研究・検証・運用基盤である。単一モデルの精度を誇示することではなく、データリークを排除した同一条件下で多数の統計・機械学習・深層学習・時系列基盤モデルを比較し、再現可能な証拠を残した上で、用途別Championを選抜する。

### 1.1 正式な評価目的

1. 主目的: 集合Hits@7を最大化する。
2. 副目的: 位置別絶対誤差±1率を最大化する。
3. 補助目的: 位置別MAE/MSE、NDCG@7、Brier、Log Loss、ECEを改善する。
4. 制約: 不正な数字、重複、昇順違反、データリーク、GPU証跡不足、未封印予測を失格とする。
5. 「MAE<1」は到達目標として監視するが、将来独立評価で成立しない限り成功と主張しない。

## 2. スコープ

### 2.1 含む

- Web/ローカルからのデータ取得、Raw保存、正規化、Canonical化
- 抽選・候補数字・位置・外生変数の特徴量生成
- StatsForecast、MLForecast、NeuralForecast、HierarchicalForecast
- AutoGluon TimeSeries、sktime、Darts、GluonTS、PyTorch Forecasting
- Hugging Face時系列基盤モデルのzero-shot/fine-tune/埋め込み利用
- Optuna/Rayによる探索、複数seed、Nested Rolling CV
- OOF校正、残差補正、Ensemble、制約付きデコード
- MLflow、OpenTelemetry、Prometheus、Grafana、Lokiによる観測
- Web UI、CLI、API、イベント、RBAC、二段階承認
- 予測封印、Release Bundle、Artifact Store、監査台帳
- Linux本番、Windows補助、Docker/OCI、systemd

### 2.2 含まない

- 当選を保証する表現や販売用途
- 将来の抽選結果を特徴量に混入する処理
- Holdoutを見ながらの反復調整
- 出所・ライセンス・revisionが不明なモデルの本番採用
- 1環境へ全依存を無条件に同居させる構成

## 3. 利用者とロール

| ロール | 主な操作 |
|---|---|
| Viewer | 予測、評価、ダッシュボード、監査証跡の閲覧 |
| Researcher | 実験定義、候補モデル登録、探索実行 |
| Operator | データ取得、定期実行、障害復旧、Shadow採点 |
| Approver | Champion昇格、Release承認、Holdout開封承認 |
| Administrator | 権限、Secret、インフラ、保持ポリシー管理 |

## 4. 機能要件

| ID | 要件 | 受入条件 |
|---|---|---|
| FR-DATA-001 | 公式/許可済みソースから取得する | Raw、取得時刻、URL、ETag、SHA-256を保存 |
| FR-DATA-002 | 文字コード・列名・区切りを正規化する | Canonical契約テストPASS |
| FR-FEAT-001 | As-of特徴量を生成する | `available_at <= forecast_created_at`を全行検証 |
| FR-MODEL-001 | 統一Model Adapterでモデルを登録する | fit/predict/save/load/capability契約PASS |
| FR-MODEL-002 | 複数ライブラリを同一評価で比較する | Leaderboardにlibrary/model/revisionを記録 |
| FR-EVAL-001 | Nested Rolling CVを行う | inner/outer foldが分離される |
| FR-EVAL-002 | 固定Holdoutを隔離する | 承認なしに開封不可、アクセス監査あり |
| FR-EVAL-003 | ±1を詳細評価する | 位置別、平均、最悪位置、全7位置成功率を出力 |
| FR-OPT-001 | Optuna/Rayで探索する | trialの設定・seed・fold・資源を保存 |
| FR-GPU-001 | 実GPU利用を証明する | trial PID、device UUID、peak VRAM、util、torch deviceを記録 |
| FR-CAL-001 | OOF校正する | 校正器が同じfoldの正解を参照しない |
| FR-ENS-001 | 非負制約Ensembleを作る | 重み合計1、単一モデル最大0.60 |
| FR-DEC-001 | 合法な7数字へ制約デコードする | 1..37、重複なし、昇順、位置合法範囲 |
| FR-OBS-001 | ログ・トレース・メトリクスを常時記録する | run_id/trial_id/fold_idで相互参照可能 |
| FR-UI-001 | 統合Web UIを提供する | データ、実験、モデル、比較、GPU、承認を操作可能 |
| FR-SEC-001 | RBACと二段階承認を行う | 自己承認不可、監査台帳へ追記 |
| FR-SEAL-001 | 予測を抽選前に封印する | HMAC/署名、外部時刻、検証CLIがPASS |

## 5. 非機能要件

| 項目 | 目標 |
|---|---|
| 再現性 | 同一Release Bundle・seed・データ版で同一予測を再現 |
| 性能 | 通常再学習・封印を抽選前3時間以内 |
| 可用性 | 失敗時に前回Championへ自動fallback |
| 監査性 | 重要操作をappend-only台帳へ記録 |
| 拡張性 | 新モデルを既存パイプライン修正なしでPlugin追加 |
| 移植性 | Linux本番、Windowsローカルsmoke、OCI認定環境 |
| セキュリティ | Secret非表示、署名、SBOM、依存脆弱性検査 |
| データ保持 | 封印予測・評価・ハッシュ永久、大容量trialは状態別保持 |

## 6. 正式な±1定義

| 指標 | 定義 |
|---|---|
| position_within_1_i | 位置iで `abs(y_i - yhat_i) <= 1` |
| mean_within_1 | 全抽選・全位置の平均成功率 |
| worst_position_within_1 | 7位置のうち最小の成功率 |
| all_positions_within_1 | 1抽選で7位置すべて±1の割合 |
| positions_within_1_count | 1抽選あたり成功位置数0..7 |
| matched_set_within_1 | 最小費用割当後に±1となる数字数 |

Champion選抜はHits@7を主順位とし、±1、校正、安定性、資源、実行時間をGateとPareto分析に使う。用途別に`champion_hits`、`champion_within1`、`champion_calibrated`を保持する。

## 7. 受入基準

- P0モデル群が全て同一Outer CVで実行可能
- 全trialの設定、予測、指標、GPU/CPU証跡が保存される
- ±1 LeaderboardとPareto Frontが生成される
- 固定Holdoutは探索完了前に参照されない
- 封印済みShadow予測を実測後に採点できる
- 重大障害注入後にresume/fallbackできる
