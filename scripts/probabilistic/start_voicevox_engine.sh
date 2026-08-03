#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-cpu}"
PORT="${VOICEVOX_PORT:-50021}"
NAME="${VOICEVOX_CONTAINER_NAME:-ppl01-voicevox}"

if curl -fsS "http://127.0.0.1:${PORT}/version" >/dev/null 2>&1; then
    echo "VOICEVOX_STATUS=ALREADY_RUNNING"
    curl -fsS "http://127.0.0.1:${PORT}/version"
    echo
    exit 0
fi

RUNTIME=""
for candidate in docker podman; do
    if command -v "$candidate" >/dev/null 2>&1; then
        RUNTIME="$candidate"
        break
    fi
done
if test -z "$RUNTIME"; then
    echo "ERROR: docker or podman is required to start VOICEVOX Engine" >&2
    exit 2
fi

case "$MODE" in
    cpu)
        IMAGE="voicevox/voicevox_engine:cpu-latest"
        EXTRA=(--cpus 2 --memory 4g)
        ;;
    gpu)
        IMAGE="voicevox/voicevox_engine:nvidia-latest"
        EXTRA=(--gpus all)
        echo "WARNING: GPU VOICEVOX competes with probabilistic GPU jobs." >&2
        ;;
    *)
        echo "Usage: $0 [cpu|gpu]" >&2
        exit 2
        ;;
esac

"$RUNTIME" rm -f "$NAME" >/dev/null 2>&1 || true
"$RUNTIME" pull "$IMAGE"
"$RUNTIME" run -d \
    --name "$NAME" \
    --restart unless-stopped \
    -p "127.0.0.1:${PORT}:50021" \
    "${EXTRA[@]}" \
    "$IMAGE" >/dev/null

for _ in $(seq 1 90); do
    if curl -fsS "http://127.0.0.1:${PORT}/version" >/dev/null 2>&1; then
        echo "VOICEVOX_STATUS=PASS"
        echo "VOICEVOX_MODE=$MODE"
        echo "VOICEVOX_URL=http://127.0.0.1:${PORT}"
        exit 0
    fi
    sleep 2
done

"$RUNTIME" logs --tail 100 "$NAME" || true
echo "ERROR: VOICEVOX did not become healthy" >&2
exit 3
