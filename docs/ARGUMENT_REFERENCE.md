# Loto Forecast Platform v2.0 — 引数・設定リファレンス

## CLI

### 共通

| 引数 | 型 | 既定値 | 説明 |
|---|---|---:|---|
| `--registry` | path/DSN | `platform.sqlite3` | 台帳SQLiteまたはPostgreSQL DSN |

### `loto data acquire`

| 引数 | 必須 | 説明 |
|---|---:|---|
| `--game` | No | `loto7/loto6/mini/bingo5/numbers3/numbers4` |
| `--output` | Yes | Raw・正規化・特徴量出力先 |
| `--source-file` | No | Web取得せずローカルRaw CSVを使用 |
| `--force` | No | ETag/更新判定を無視して再取得 |
| `--postgres-dsn` | No | 生成テーブルをPostgreSQLにも保存 |

### `loto experiment run-all`

`data acquire`の全引数に加え、`--backtest-draws`で軽量運用経路の評価抽選数を指定する。

### `loto experiment research`

| 引数 | 必須 | 説明 |
|---|---:|---|
| `--config` | Yes | v2研究設定YAML。未知キーはエラー |

### `loto models`

- `models list [--priority p0|p1|p2] [--available-only] [--format table|json]`
- `models show MODEL_ID`

### `loto config validate`

- `--file`: 入力YAML
- `--write-resolved`: 既定値展開後の設定を書き出す

## YAML設定

### `data`

| キー | 型 | 既定値 | 制約 |
|---|---|---:|---|
| `game` | string | `loto7` | Lottery Plugin ID |
| `input` | path | 必須 | Canonical変換可能なCSV |
| `target_mode` | enum | `both` | `candidate/position/both` |
| `feature_windows` | int[] | `[5,10,20,30,50,100]` | 正・重複除去 |
| `exponential_halflives` | float[] | `[5,10,20,50]` | 正の値 |
| `min_train_draws` | int | 100 | 学習開始下限 |

### `cv`

| キー | 既定値 | 説明 |
|---|---:|---|
| `outer_folds` | 5 | モデルファミリー比較 |
| `inner_folds` | 3 | パラメータ・特徴量選択 |
| `test_size` | 20 | foldあたりの将来抽選数 |
| `gap` | 0 | train/test間のembargo |
| `expanding` | true | expandingまたはfixed window |
| `holdout_size` | 50 | 自動研究から隔離する固定Holdout |
| `seeds` | `[42,1729,20260730]` | multi-seed |
| `min_train_size` | 100 | 最小学習抽選数 |

### `objective`

- `primary`: `mean_hits_at_7/mean_within_1/all_positions_within_1`
- `weights`: 複合スコアの指標→重み。損失指標は負値。
- `calibration_brier_relative_limit`: 校正非劣性上限。
- `max_single_ensemble_weight`: 非負Ensembleの一モデル上限。

### `search`

| キー | 選択肢・説明 |
|---|---|
| `backend` | `none/optuna/ray` |
| `trials` | outer foldごとの試行数 |
| `timeout_seconds` | 探索タイムアウト |
| `parallel_jobs` | Optuna並列数 |
| `cpus_per_trial` | Ray resource |
| `gpus_per_trial` | Ray fractional GPU対応 |
| `fail_fast` | 1 trial失敗で全体停止するか |
| `max_consecutive_failures` | 非進捗停止閾値 |
| `sampler` | `tpe/random/cmaes` |
| `pruner` | `median/hyperband/none` |

### `runtime`

- `output`
- `device`: `auto/cpu/cuda`
- `precision`: `32/16-mixed/bf16-mixed`
- `deterministic`
- `cache_dir`
- `worker_isolation`: `inprocess/subprocess/container`
- `model_timeout_seconds`
- `max_memory_mb`
- `resume`

### `observability`

- `mlflow_uri`, `experiment_name`
- `jsonl_log`, `log_level`
- `prometheus_port`
- `otlp_endpoint`, `trace_sample_ratio`
- `capture_gpu`, `capture_process_tree`
- `profile`: `none/py-spy/torch`

## モデル固有引数

`model_params.MODEL_ID`で上書きする。定義済み探索空間は`src/loto/optimization/search.py`、既定値と能力は`loto models show MODEL_ID`を正本とする。未知のモデルIDと未知設定キーはSilent fallbackせずエラーにする。
