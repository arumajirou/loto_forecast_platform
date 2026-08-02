#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT/scripts/run_scheduled_pipeline.sh"
MARK_BEGIN="# >>> loto-ops schedule >>>"
MARK_END="# <<< loto-ops schedule <<<"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
( crontab -l 2>/dev/null || true ) | awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
$0 == begin {skip=1; next}
$0 == end {skip=0; next}
skip != 1 {print}
' > "$TMP"
cat >> "$TMP" <<CRON
$MARK_BEGIN
30 6 * * 1-5 $RUNNER weekday_daily >> $ROOT/logs/scheduler/cron_dispatch.log 2>&1
@reboot $RUNNER pc_startup >> $ROOT/logs/scheduler/cron_reboot_dispatch.log 2>&1
$MARK_END
CRON
crontab "$TMP"
echo "Installed compatibility cron entries. systemd user services are recommended."
