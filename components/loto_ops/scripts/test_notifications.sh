#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ENV="${LOTO_OPS_RUNTIME_ENV:-$HOME/.config/loto-ops/runtime.env}"
if [[ ! -f "$RUNTIME_ENV" ]]; then
    echo "ERROR: missing $RUNTIME_ENV" >&2
    echo "Run: $ROOT/scripts/configure_runtime.sh" >&2
    exit 2
fi
set -a
# shellcheck disable=SC1090
source "$RUNTIME_ENV"
set +a
exec "$ROOT/run_loto_ops.sh" notify-test \
    --reason manual_notification_test \
    --message "Loto Ops Gmail/Slack notification test" \
    --fail-on-error
