# 参照3リポジトリと統合先の対応表

- 統合版: Loto Forecast Platform 2.1.0
- 作成日: 2026-07-30
- 統合先: `loto_forecast_platform_integrated`
- 原則: 参照リポジトリは変更せず、機能を統合先へ再実装・接続する

## 1. 参照元

| 参照元 | Git revision | 元の責務 | v2.1の統合先 |
|---|---|---|---|
| `arumajirou/loto_life_feature_pipeline` | `3955a15c64bd5af9a7c2b30975f5f50126ec4d3a` | CSV取得、文字コード・列推定、正規化、抽選／候補特徴量 | `src/loto/data/*`, `src/loto/features/legacy.py` |
| `arumajirou/loto_ops_pipeline` | `dbf885814575f65a6871f80b66429ff4e4474f76` | DB、分析、定期実行、進捗、通知、Web運用 | `src/loto/data/datasets.py`, `notifications.py`, `scheduling.py`, API/UI |
| `arumajirou/loto_neuralforecast_pipeline` | `7b3e0171372a9fbea5b5ad0cc2cc522f1abba5eb` | NeuralForecast学習・予測・検証、UI、Model Lab、観測 | `models/catalog.py`, `neuralforecast_adapter.py`, `workers.py`, API Model Lab |

## 2. 取得対象

| key | ゲーム | CSV endpoint | 種別 | 主数字／桁 | Bonus | 抽選曜日（0=月） |
|---|---|---|---|---:|---:|---|
| `mini` | ミニロト | `https://loto-life.net/csv/mini` | lotto | 5 | 1 | 火 |
| `loto6` | ロト6 | `https://loto-life.net/csv/loto6` | lotto | 6 | 1 | 月・木 |
| `loto7` | ロト7 | `https://loto-life.net/csv/loto7` | lotto | 7 | 2 | 金 |
| `bingo5` | ビンゴ5 | `https://loto-life.net/csv/bingo5` | bingo | 8 | 0 | 水 |
| `numbers3` | ナンバーズ3 | `https://loto-life.net/csv/numbers3` | digits | 3桁 | 0 | 月〜金 |
| `numbers4` | ナンバーズ4 | `https://loto-life.net/csv/numbers4` | digits | 4桁 | 0 | 月〜金 |

取得処理はログイン回避、CAPTCHA回避、アクセス制限突破を行わない。HTTP response、URL、取得時刻、byte数、SHA-256を記録する。

## 3. データ変換

```text
HTTPまたはローカルCSV
  -> raw/{game}.csv + fetch metadata
  -> encoding/separator detection
  -> column inference and normalization
  -> quality gate
  -> draw_features
  -> occurrence_features
  -> CSV / SQLite / optional Parquet
  -> Stage manifest / events.jsonl / acquisition_report.json
```

### 正規化項目

共通: `game`, `game_display_name`, `source_url`, `draw_no`, `draw_date`, calendar columns。

Lotto/Bingo: `n1..nN`, `bonus1..bonusN`。

Numbers: `draw_number_text`, `d1..dN`。先頭0を失わない。

### 品質ゲート

- 回号重複
- 日付変換失敗
- 必須数字欠損
- 値域違反
- 主数字の重複
- 主数字の昇順違反
- Numbers桁数違反
- 入出力frame fingerprint

## 4. 特徴量

### 抽選単位

- 合計、平均、標準偏差、最小、最大、範囲
- 奇数／偶数、素数、低／中／高レンジ
- mod 3分布
- 連番ペア、最長連番
- gap平均／最小／最大
- 末尾一意数、entropy
- 5／10／20／50回のshift(1)済みrolling平均・標準偏差
- 各候補のhitとshift(1)済みrolling頻度
- Numbers: 桁合計、桁分散、重複、一意数、entropy、単調増加／減少

### 候補数字単位

- `hit_current`
- `target_hit_next`
- `gap_since_seen`
- `freq_last_5/10/20/50`
- `seen_last_5/10/20/50`
- candidate parity、mod3、mod10

Loto7の研究用候補特徴量は、現在行を参照せず更新を行うため、`freq_w*`, `freq_all`, `gap_draws`, `freq_exp`をas-ofで生成する。

## 5. 運用機能

| 機能 | 統合方法 |
|---|---|
| 全ゲーム一括実行 | `loto data acquire --games all` |
| local source再現 | `--source-map` |
| 日程計画 | `loto schedule plan` |
| 排他 | `RunLock`、原子的lock file |
| 通知 | local JSONL、Slack／generic webhook、SMTP |
| 通知安全策 | 外部送信は既定OFF、環境変数で明示的に有効化 |
| 進捗／ログ | Stage event JSONL、research events JSONL |
| 資源 | process tree、CPU、RSS、GPU snapshot |
| UI | run/model/game/leaderboard/Model Parameter Lab |
| API | `/api/v2/*`, OpenAPI, Prometheus |

## 6. NeuralForecast統合

- 33 AutoModelを宣言的カタログへ登録
- `backend=optuna|ray`
- 小試行はRandom、通常Optunaはmultivariate TPE、RayはBasicVariantまたはOptunaSearch
- FFTモデルのhalf precisionをFP32へ補正
- multivariateモデルの`n_series`必須検証
- Optunaでは固定YAML configをcallableへ変換
- optional package未導入時は`UNAVAILABLE`／`FAILED`とし、代替モデルへ偽装しない

## 7. 非移植事項

参照実装のコードをそのまま複製せず、統合先の契約、監査、RBAC、Artifact Store、封印、評価器へ合わせて再実装した。破壊的DB reset、無承認外部送信、未認定GPU処理は自動化していない。
