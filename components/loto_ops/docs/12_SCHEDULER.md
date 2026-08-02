# Scheduler / 定期実行設計

## 目的

Loto Ops Pipelineを以下のタイミングで自動実行します。

- 平日24時（月〜金 00:00）
- WSL起動時（cron @reboot、任意で /etc/wsl.conf boot command）
- Kubuntu起動時（user systemd service、desktop autostart）

## 作成ファイル

```text
scripts/run_scheduled_pipeline.sh
scripts/install_cron_schedule.sh
scripts/install_kubuntu_startup.sh
scripts/install_wsl_startup.sh
scripts/check_schedule.sh
logs/scheduler/last_run.json
logs/scheduler/*.log
~/.config/systemd/user/loto-ops-startup.service
~/.config/autostart/loto-ops-startup.desktop
```

## CLI

```bash
cd /mnt/e/env/ts/loto_ops
source ./activate_env.sh

loto-ops schedule-install-cron
loto-ops schedule-install-kubuntu-startup
loto-ops schedule-install-wsl-startup
loto-ops schedule-status
loto-ops schedule-run-now --reason manual
```

## Cron

登録される内容は以下です。

```cron
0 0 * * 1-5 /mnt/e/env/ts/loto_ops/scripts/run_scheduled_pipeline.sh weekday_midnight
@reboot /mnt/e/env/ts/loto_ops/scripts/run_scheduled_pipeline.sh reboot
```

## Kubuntu

`loto-ops schedule-install-kubuntu-startup` は以下を作成します。

```text
~/.config/systemd/user/loto-ops-startup.service
~/.config/autostart/loto-ops-startup.desktop
```

## WSL

通常はcron @rebootを使います。WSLの完全起動時に実行したい場合のみ、以下を実行します。

```bash
loto-ops schedule-install-wsl-startup --write-wsl-conf
```

この場合はWindows側で以下を実行してWSLを再起動します。

```powershell
wsl --shutdown
```

## 確認

```bash
loto-ops schedule-status
cat logs/scheduler/last_run.json
tail -n 200 logs/scheduler/*.log
```


## v3.6: 外部プロジェクトパス欠損時の安全動作

`loto_life_feature_pipeline` が見つからない状態で定期実行すると、更新処理は安全にスキップされます。既存DBテーブルを壊さないため、`scrape`、`build-dataset-fast`、`load-postgres-fast` は実行しません。

確認:

```bash
loto-ops path-status
loto-ops schedule-status
```

修正例:

```bash
export LOTO_LIFE_PROJECT=/mnt/e/env/fc/loto_life_feature_pipeline
# または configs/loto_ops.yaml の paths.loto_life_project を修正
```
