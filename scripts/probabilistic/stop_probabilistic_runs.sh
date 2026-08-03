#!/usr/bin/env bash
set -euo pipefail

mapfile -t PIDS < <(pgrep -f '([u]v run loto3|[/]loto3) probabilistic run' || true)
if test "${#PIDS[@]}" -eq 0; then
    echo "PROBABILISTIC_PROCESS=STOPPED"
    exit 0
fi

echo "Sending SIGINT to: ${PIDS[*]}"
kill -INT "${PIDS[@]}" 2>/dev/null || true
for _ in $(seq 1 20); do
    sleep 1
    if ! pgrep -f '([u]v run loto3|[/]loto3) probabilistic run' >/dev/null; then
        echo "PROBABILISTIC_PROCESS=STOPPED"
        exit 0
    fi
done

echo "Sending SIGTERM"
mapfile -t PIDS < <(pgrep -f '([u]v run loto3|[/]loto3) probabilistic run' || true)
test "${#PIDS[@]}" -eq 0 || kill -TERM "${PIDS[@]}" 2>/dev/null || true
sleep 3
pgrep -af '([u]v run loto3|[/]loto3) probabilistic run' || echo "PROBABILISTIC_PROCESS=STOPPED"
