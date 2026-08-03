#!/usr/bin/env bash
set -euo pipefail
NAME="${VOICEVOX_CONTAINER_NAME:-ppl01-voicevox}"
for runtime in docker podman; do
    if command -v "$runtime" >/dev/null 2>&1; then
        "$runtime" rm -f "$NAME" >/dev/null 2>&1 || true
    fi
done
echo "VOICEVOX_STATUS=STOPPED"
