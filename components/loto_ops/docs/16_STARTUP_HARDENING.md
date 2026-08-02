# Startup hardening

Kubuntu 起動時、cron @reboot、KDE autostart はほぼ同時に走ることがあるため、v3.11 では以下を入れています。

- cron/systemd/KDE autostart 用 PATH 固定
- `UV_BIN` による uv 実行ファイル検出
- 起動直後DNS未準備対策の sleep
- startup/reboot/autostart 多重実行の cooldown
- progress.json の実行開始時リセット

環境変数:

```bash
export LOTO_OPS_STARTUP_DELAY_SECONDS=60
export LOTO_OPS_DESKTOP_AUTOSTART_DELAY_SECONDS=120
export LOTO_OPS_STARTUP_COOLDOWN_SECONDS=900
export UV_BIN=/home/az/.local/bin/uv
```
