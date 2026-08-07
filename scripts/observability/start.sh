#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="$ROOT/deploy/observability"
ENV_FILE="${OBSERVABILITY_ENV_FILE:-$DEPLOY/.env}"

command -v docker >/dev/null || { echo "BLOCKED: docker is unavailable"; exit 20; }
docker compose version >/dev/null

python "$ROOT/scripts/observability/validate_stack.py" --require-lock
# shellcheck disable=SC1091
source "$DEPLOY/images.lock.env"
export GRAFANA_IMAGE ALLOY_IMAGE PROMETHEUS_IMAGE LOKI_IMAGE TEMPO_IMAGE BUSYBOX_IMAGE

if [[ ! -f "$ENV_FILE" ]]; then
  ENV_FILE="$DEPLOY/.env.example"
fi
for name in grafana_admin_user grafana_admin_password; do
  path="$DEPLOY/secrets/$name"
  [[ -s "$path" ]] || { echo "BLOCKED: missing secret file $path"; exit 21; }
  mode="$(stat -c '%a' "$path")"
  (( 10#$mode <= 600 )) || { echo "BLOCKED: $path mode must be 0600 or stricter"; exit 22; }
done

docker compose --env-file "$ENV_FILE" -f "$DEPLOY/compose.yaml" config >/dev/null
docker compose --env-file "$ENV_FILE" -f "$DEPLOY/compose.yaml" up -d
"$ROOT/scripts/observability/smoke.sh"
read -r -p "Enterキーで終了します..." _
