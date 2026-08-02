#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TIME_VALUE="${1:-06:30}"
UI_PORT="${2:-8520}"
HOUR="${TIME_VALUE%:*}"
MINUTE="${TIME_VALUE#*:}"
UNIT_DIR="${LOTO_OPS_UNIT_DIR:-$HOME/.config/systemd/user}"
AUTOSTART_DIR="${LOTO_OPS_AUTOSTART_DIR:-$HOME/.config/autostart}"
RUNTIME_ENV="${LOTO_OPS_RUNTIME_ENV:-$HOME/.config/loto-ops/runtime.env}"
NO_SYSTEMCTL="${LOTO_OPS_NO_SYSTEMCTL:-0}"

[[ "$HOUR" =~ ^[0-9]{1,2}$ && "$MINUTE" =~ ^[0-9]{1,2}$ ]] || {
    echo "ERROR: time must be HH:MM" >&2
    exit 2
}

if [[ ! -x "$ROOT/.venv/bin/python" && "${LOTO_OPS_ALLOW_SYSTEM_PYTHON:-0}" != "1" ]]; then
    echo "ERROR: missing .venv. Run bash $ROOT/setup_linux.sh first." >&2
    exit 3
fi
if [[ ! -f "$RUNTIME_ENV" ]]; then
    echo "ERROR: missing $RUNTIME_ENV" >&2
    echo "Run $ROOT/scripts/configure_runtime.sh first." >&2
    exit 4
fi

mkdir -p "$UNIT_DIR" "$AUTOSTART_DIR" "$ROOT/logs/scheduler"
chmod +x "$ROOT/scripts/run_scheduled_pipeline.sh" "$ROOT/run_loto_ops.sh"

cat > "$UNIT_DIR/loto-ops-ui.service" <<SERVICE
[Unit]
Description=Loto Ops Streamlit UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=-$RUNTIME_ENV
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=$ROOT
ExecStart=$ROOT/.venv/bin/python -m streamlit run $ROOT/src/loto_ops/webapp/app.py --server.address 127.0.0.1 --server.port $UI_PORT --server.headless true
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
SERVICE

cat > "$UNIT_DIR/loto-ops-startup.service" <<SERVICE
[Unit]
Description=Loto Ops pipeline once at PC login
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=-$RUNTIME_ENV
WorkingDirectory=$ROOT
ExecStartPre=/usr/bin/sleep 45
ExecStart=$ROOT/scripts/run_scheduled_pipeline.sh pc_startup
TimeoutStartSec=infinity
Restart=on-failure
RestartSec=60

[Install]
WantedBy=default.target
SERVICE

cat > "$UNIT_DIR/loto-ops-weekday.service" <<SERVICE
[Unit]
Description=Loto Ops weekday pipeline
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=-$RUNTIME_ENV
WorkingDirectory=$ROOT
ExecStart=$ROOT/scripts/run_scheduled_pipeline.sh weekday_daily
TimeoutStartSec=infinity
Restart=on-failure
RestartSec=60
SERVICE

cat > "$UNIT_DIR/loto-ops-weekday.timer" <<TIMER
[Unit]
Description=Run Loto Ops once Monday through Friday

[Timer]
OnCalendar=Mon..Fri *-*-* ${HOUR}:${MINUTE}:00
Persistent=true
AccuracySec=1min

[Install]
WantedBy=timers.target
TIMER

cat > "$AUTOSTART_DIR/loto-ops-open-ui.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Loto Ops UI
Comment=Open the local Loto Ops Streamlit dashboard
Exec=/usr/bin/bash -lc 'sleep 15; /usr/bin/xdg-open http://127.0.0.1:$UI_PORT'
Terminal=false
X-GNOME-Autostart-enabled=true
DESKTOP
chmod 700 "$AUTOSTART_DIR/loto-ops-open-ui.desktop"

if [[ "$NO_SYSTEMCTL" != "1" ]]; then
    systemctl --user daemon-reload
    systemctl --user enable --now loto-ops-ui.service
    systemctl --user enable loto-ops-startup.service
    systemctl --user enable --now loto-ops-weekday.timer
    if command -v loginctl >/dev/null 2>&1 && [[ "${LOTO_OPS_ENABLE_LINGER:-1}" == "1" ]]; then
        loginctl enable-linger "$USER" 2>/dev/null || echo "WARNING: enable-linger failed; startup services will run at desktop login." >&2
    fi
fi

cat <<STATUS
Installed:
  $UNIT_DIR/loto-ops-ui.service
  $UNIT_DIR/loto-ops-startup.service
  $UNIT_DIR/loto-ops-weekday.service
  $UNIT_DIR/loto-ops-weekday.timer
  $AUTOSTART_DIR/loto-ops-open-ui.desktop

UI: http://127.0.0.1:$UI_PORT
Weekday schedule: Monday-Friday $TIME_VALUE
Startup pipeline: enabled for next login; same-day duplicate runs are skipped.
STATUS
