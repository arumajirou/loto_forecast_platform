#!/usr/bin/env bash
set -euo pipefail

ROOT="/mnt/e/env/ts/loto_ops"
RUNNER="$ROOT/scripts/run_scheduled_pipeline.sh"
OUT_DIR="$ROOT/logs/scheduler"
WSL_BOOT_SCRIPT="$ROOT/scripts/wsl_boot_loto_ops.sh"
USER_NAME="${SUDO_USER:-$USER}"
WRITE_WSL_CONF="${1:-}"

mkdir -p "$OUT_DIR"
chmod +x "$RUNNER"

cat > "$WSL_BOOT_SCRIPT" <<WSL
#!/usr/bin/env bash
set -euo pipefail
if command -v sudo >/dev/null 2>&1; then
  sudo -u "$USER_NAME" bash "$RUNNER" wsl_boot >> "$OUT_DIR/wsl_boot_dispatch.log" 2>&1 || true
else
  bash "$RUNNER" wsl_boot >> "$OUT_DIR/wsl_boot_dispatch.log" 2>&1 || true
fi
WSL
chmod +x "$WSL_BOOT_SCRIPT"

# WSL側は cron @reboot も併用します。
"$ROOT/scripts/install_cron_schedule.sh"

echo "created: $WSL_BOOT_SCRIPT"

if [ "$WRITE_WSL_CONF" = "--write-wsl-conf" ]; then
  if ! grep -qi microsoft /proc/version 2>/dev/null; then
    echo "warning: this does not look like WSL; /etc/wsl.conf was not modified" >&2
    exit 0
  fi
  sudo cp -a /etc/wsl.conf "/etc/wsl.conf.loto_ops_backup_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
  if ! sudo grep -q '^\[boot\]' /etc/wsl.conf 2>/dev/null; then
    printf '\n[boot]\ncommand=%s\n' "$WSL_BOOT_SCRIPT" | sudo tee -a /etc/wsl.conf >/dev/null
  elif sudo grep -q '^command=' /etc/wsl.conf 2>/dev/null; then
    echo "[manual] /etc/wsl.conf already has a boot command. Please merge this command:" >&2
    echo "$WSL_BOOT_SCRIPT" >&2
  else
    sudo sed -i "/^\[boot\]/a command=$WSL_BOOT_SCRIPT" /etc/wsl.conf
  fi
  echo "updated /etc/wsl.conf. Windows側で wsl --shutdown 後に再起動してください。"
else
  echo "WSL完全起動時に実行したい場合の任意コマンド:"
  echo "  sudo $0 --write-wsl-conf"
fi
