# 13 Progress Display Design

## 目的

長時間処理になりやすい `scrape`、`build-dataset-fast`、`load-postgres-fast`、`build-exog`、`build-unified`、`analyze`、`package` の進捗を、CLI・cron/systemdログ・Streamlit UI の3箇所で確認できるようにする。

## 追加ファイル

```text
src/loto_ops/progress.py
scripts/update_progress.py
logs/pipeline_progress.json
logs/scheduler/progress.json
```

## 表示方式

CLIでは以下の形式で表示する。

```text
[progress] ███████████░░░░░░░░░░░░░░░  40.00% | RUN 2/5 load postgres
```

スケジュール実行では `logs/scheduler/progress.json` に現在状態を保存する。
Streamlitの `Scheduler` ページはこのJSONを読み、`st.progress` で表示する。

## 対象コマンド

```bash
loto-ops build-dataset-fast --engine auto
loto-ops load-postgres-fast --jobs 6
loto-ops build-exog --parallel-workers 16
loto-ops build-unified
loto-ops analyze
loto-ops package --mode light
loto-ops run-all-fast --engine auto --jobs 6 --with-exog --parallel-workers 16 --with-analysis
loto-ops schedule-run-now --reason manual
```

## 進捗確認

```bash
cat /mnt/e/env/ts/loto_ops/logs/pipeline_progress.json
cat /mnt/e/env/ts/loto_ops/logs/scheduler/progress.json
```

## 注意

`build-unified` の内部処理は外部プロジェクト `loto_forecast_project` 側のCLIを呼び出すため、現時点では高水準の段階進捗を表示する。外部CLIが出す `[exog 1/6]` のようなログは、Streamlitの直近ログ欄で確認する。
