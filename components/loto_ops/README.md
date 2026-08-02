# Loto Ops v3 — Short Path + OSS UI + Automation

推奨配置先: `/mnt/e/env/ts/loto_ops`

```bash
cd /mnt/e/env/ts/loto_ops
bash install_automation.sh 06:30 8520
```

- OSS UI: Streamlit (`http://127.0.0.1:8520`)
- PC起動時: UIとパイプラインを起動
- 月〜金06:30: 1日1回実行
- Gmail/Slack: 成功・失敗を通知

詳細: [AUTOMATION_SETUP.md](AUTOMATION_SETUP.md) / [MIGRATION.md](MIGRATION.md)

---

# Repaired distribution notice

This archive contains the restored full operations CLI plus the legacy-compatible `run` and handover commands. Start with [SETUP.md](SETUP.md) and review [REPAIR_REPORT.md](REPAIR_REPORT.md). The packaged verification result is **104 passed**.

# loto_ops_pipeline

`loto_ops_pipeline` は、既存の `loto_life_feature_pipeline` と `loto_forecast_project` を壊さず、上位から統合運用するためのデータ基盤アプリです。

目的は以下です。

- loto-life CSV取得
- 正規化済みCSVから既存プロジェクト互換データセット作成
- SQLite保存
- PostgreSQL `dataset.*` への `COPY` ロード
- `exog` 特徴量生成
- `dataset.loto_y_ts_unified` 作成
- テーブル確認Webアプリ
- 品質・メタ分析
- ブラウザ提出用ZIP作成
- systemd user timer による毎日定期実行

## 推奨配置

```bash
cd /mnt/e/env/fc
unzip -o /mnt/e/env/fc/zips/loto_ops_pipeline.zip -d /mnt/e/env/fc
cd /mnt/e/env/ts/loto_ops
```

## セットアップ

```bash
./scripts/setup_uv.sh
```

## 入口コマンド

```bash
uv run loto-ops preflight
uv run loto-ops run-all --with-exog --with-analysis --with-zip
uv run loto-ops webapp --port 8520
uv run loto-ops package --mode light
```

## 安全設計

DB削除やリセットは `--confirm-reset` または `--confirm-drop-db` が無いと実行されません。
`run_id` ごとに `runs/{run_id}` にログ・manifest・メトリクスを保存します。

## 重要: build-dataset と PostgreSQL投入の責務

`loto-ops build-dataset` は SQLite の `dataset_loto_y_ts` / `dataset_loto_hist_feat` 作成までを成功条件にします。既存の `loto_life_feature_pipeline` 側スクリプトが PostgreSQL `to_sql` で失敗しても、SQLiteが完成していれば次の `loto-ops load-postgres` で `psql \copy` により安全にPostgreSQLへ投入します。



## 高速モード v3

CPU使用率が低い場合は、従来の `build-dataset` / `load-postgres` ではなく高速モードを使います。

```bash
cd /mnt/e/env/ts/loto_ops
export POLARS_MAX_THREADS=24
export RAYON_NUM_THREADS=24
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

uv run loto-ops build-dataset-fast --engine auto
uv run loto-ops load-postgres-fast --jobs 6
uv run loto-ops build-exog --parallel-workers 16
uv run loto-ops build-unified
```

一括版:

```bash
uv run loto-ops run-all-fast --engine auto --jobs 6 --with-exog --parallel-workers 16 --with-analysis
```

高速モードの方針:

- pandas `to_sql` の巨大INSERTを使わない
- SQLite/CSV/Parquet生成までをデータセット作成の責務にする
- PostgreSQL投入は `UNLOGGED staging table` + 並列 `psql \copy` に統一する
- ゲーム別CSVパーティションを並列投入する
- Polarsが利用可能なら縦持ち変換・rolling計算をPolarsで行う

## 仮想環境の有効化

通常セットアップ:

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/setup_uv.sh
source ./activate_env.sh
```

`source` で読み込むと、現在のシェルで `.venv`、`PYTHONPATH`、高速化用スレッド設定が有効になります。

```bash
which python
which loto-ops
loto-ops --help
```

セットアップと有効化を同時に行う場合:

```bash
cd /mnt/e/env/ts/loto_ops
source scripts/setup_and_activate.sh
```

新しい有効化済みシェルを開く場合:

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/enter_env.sh
```

終了は通常のPython仮想環境と同じです。

```bash
deactivate
```


## 定期実行

```bash
source ./activate_env.sh
loto-ops schedule-install-cron
loto-ops schedule-install-kubuntu-startup
loto-ops schedule-install-wsl-startup
loto-ops schedule-status
```

Webアプリの `Scheduler` ページからも登録、確認、手動実行できます。


## Progress bars / progress.json

v3.7 adds progress display for CLI, scheduled runs, and the Streamlit UI.

```bash
cd /mnt/e/env/ts/loto_ops
source ./activate_env.sh

# Progress bar in terminal and JSON state in logs/pipeline_progress.json
loto-ops run-all-fast --engine auto --jobs 6 --with-exog --parallel-workers 16 --with-analysis

# Individual commands also print progress lines
loto-ops build-dataset-fast --engine auto
loto-ops load-postgres-fast --jobs 6
loto-ops build-exog --parallel-workers 16
loto-ops build-unified
loto-ops analyze

# Scheduled pipeline progress
loto-ops schedule-run-now --reason manual_progress_check
cat logs/scheduler/progress.json
```

The web app `Pipeline Run` page now shows a progress bar and live logs while running commands. The `Scheduler` page reads `logs/scheduler/progress.json` and also displays live progress during manual scheduled runs.


## v3.8 高速化再設計

通常運用は `light` モードを使う。

```bash
cd /mnt/e/env/ts/loto_ops
source ./activate_env.sh

loto-ops perf-status --mode auto
loto-ops run-all-fast --mode light --with-exog --with-analysis --package light
```

`build-unified` は標準で PostgreSQL CTAS 型の高速経路を使う。

```bash
loto-ops build-unified-fast --mode light
loto-ops build-unified --engine fast --mode light
```

重い研究用exogを日次処理から外す場合:

```bash
loto-ops exog-mode light
```

詳細は `docs/14_PERFORMANCE_REDESIGN.md` を参照。


## v3.9 setup note

CLIだけ使う場合はWeb依存を入れません。ネットワークタイムアウト時も `loto-ops` を優先復旧します。

```bash
cd /mnt/e/env/ts/loto_ops
./scripts/setup_uv.sh
source ./activate_env.sh
loto-ops --help
```

Webアプリを使う場合だけ追加で実行します。

```bash
./scripts/setup_web.sh
```


## v3_10 note

Scheduled runs now accept `skipped` progress status for optional full packaging, so `LOTO_OPS_PACKAGE_FULL=0` does not fail the pipeline.

## Notifications: Gmail / Slack

実行結果をメール・Slackへ通知する場合:

```bash
cd /mnt/e/env/ts/loto_ops
cp configs/notify.env.example configs/notify.env
chmod 600 configs/notify.env
nano configs/notify.env
source ./activate_env.sh
./scripts/test_notify.sh
```

定期実行では `scripts/run_scheduled_pipeline.sh` の終了時に自動で `loto-ops notify-run-summary` が呼ばれます。
