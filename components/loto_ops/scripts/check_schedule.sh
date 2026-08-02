#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
echo "project: $ROOT"
echo "UI: http://127.0.0.1:8520"
echo
echo "=== systemd user units ==="
systemctl --user status loto-ops-ui.service --no-pager 2>/dev/null || true
systemctl --user status loto-ops-startup.service --no-pager 2>/dev/null || true
systemctl --user status loto-ops-weekday.timer --no-pager 2>/dev/null || true
echo
echo "=== timers ==="
systemctl --user list-timers loto-ops-weekday.timer --all --no-pager 2>/dev/null || true
echo
echo "=== last run ==="
cat "$ROOT/logs/scheduler/last_run.json" 2>/dev/null || echo "no last_run.json"
echo
echo "=== progress ==="
cat "$ROOT/logs/scheduler/progress.json" 2>/dev/null || echo "no progress.json"
