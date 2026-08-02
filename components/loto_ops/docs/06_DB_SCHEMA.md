# DBスキーマ仕様

## dataset.loto_y_ts

| column | type | description |
|---|---|---|
| loto | text | ゲーム名 |
| ds | date | 抽せん日 |
| unique_id | text | N1, N2など |
| ts_type | text | raw, cumsumなど |
| y | double | 目的値 |
| exec_ts | timestamp | 実行時刻 |
| updated_ts | timestamp | 更新時刻 |
| proc_seconds | double | 処理秒数 |

## dataset.loto_hist_feat

`loto`, `ds`, `unique_id` と `hist_` プレフィックスの履歴特徴量を持つ。

## dataset.loto_y_ts_unified

`loto_y_ts` に履歴特徴量と外生特徴量を結合した学習用データセット。
