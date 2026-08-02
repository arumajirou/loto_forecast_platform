#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TIME_VALUE="${1:-06:30}"
UI_PORT="${2:-8520}"

bash "$ROOT/setup_linux.sh"
bash "$ROOT/scripts/configure_runtime.sh"
bash "$ROOT/scripts/test_notifications.sh"
bash "$ROOT/scripts/install_user_services.sh" "$TIME_VALUE" "$UI_PORT"

cat <<DONE
AUTOMATION SETUP PASS
UI: http://127.0.0.1:$UI_PORT
Weekdays: $TIME_VALUE
Status: $ROOT/run_loto_ops.sh schedule-status
DONE
