#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="$ROOT/deploy/observability"
ENV_FILE="${OBSERVABILITY_ENV_FILE:-$DEPLOY/.env}"
[[ -f "$ENV_FILE" ]] || ENV_FILE="$DEPLOY/.env.example"
command -v docker >/dev/null || { echo "BLOCKED: docker is unavailable"; exit 20; }
# shellcheck disable=SC1091
source "$DEPLOY/images.lock.env"
export GRAFANA_IMAGE ALLOY_IMAGE PROMETHEUS_IMAGE LOKI_IMAGE TEMPO_IMAGE BUSYBOX_IMAGE
docker compose --env-file "$ENV_FILE" -f "$DEPLOY/compose.yaml" down
read -r -p "Enterキーで終了します..." _
