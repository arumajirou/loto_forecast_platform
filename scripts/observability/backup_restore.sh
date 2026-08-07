#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="$ROOT/deploy/observability"
ENV_FILE="${OBSERVABILITY_ENV_FILE:-$DEPLOY/.env}"
[[ -f "$ENV_FILE" ]] || ENV_FILE="$DEPLOY/.env.example"
ACTION="${1:-}"
BACKUP_DIR="${2:-$DEPLOY/backups/$(date -u +%Y%m%dT%H%M%SZ)}"
PROJECT="loto-observability"
VOLUMES=(grafana_data prometheus_data loki_data tempo_data alloy_data)

command -v docker >/dev/null || { echo "BLOCKED: docker is unavailable"; exit 20; }
python "$ROOT/scripts/observability/validate_stack.py" --require-lock
# shellcheck disable=SC1091
source "$DEPLOY/images.lock.env"
export GRAFANA_IMAGE ALLOY_IMAGE PROMETHEUS_IMAGE LOKI_IMAGE TEMPO_IMAGE BUSYBOX_IMAGE

compose() {
  docker compose --env-file "$ENV_FILE" -f "$DEPLOY/compose.yaml" "$@"
}

backup() {
  mkdir -p "$BACKUP_DIR"
  compose stop
  for suffix in "${VOLUMES[@]}"; do
    volume="${PROJECT}_${suffix}"
    docker volume inspect "$volume" >/dev/null
    docker run --rm \
      -v "$volume:/source:ro" \
      -v "$BACKUP_DIR:/backup" \
      "$BUSYBOX_IMAGE" \
      sh -c "cd /source && tar -czf /backup/${suffix}.tar.gz ."
  done
  (cd "$BACKUP_DIR" && sha256sum ./*.tar.gz > SHA256SUMS)
  printf '%s\n' "BACKUP_STATUS=PASS" "BACKUP_DIR=$BACKUP_DIR"
}

restore() {
  [[ "${CONFIRM_RESTORE:-NO}" == "YES" ]] || {
    echo "BLOCKED: set CONFIRM_RESTORE=YES for destructive restore"
    exit 30
  }
  [[ -f "$BACKUP_DIR/SHA256SUMS" ]] || { echo "BLOCKED: SHA256SUMS missing"; exit 31; }
  (cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)
  compose down
  for suffix in "${VOLUMES[@]}"; do
    archive="$BACKUP_DIR/${suffix}.tar.gz"
    [[ -f "$archive" ]] || { echo "BLOCKED: missing $archive"; exit 32; }
    volume="${PROJECT}_${suffix}"
    docker volume create "$volume" >/dev/null
    docker run --rm \
      -v "$volume:/target" \
      -v "$BACKUP_DIR:/backup:ro" \
      "$BUSYBOX_IMAGE" \
      sh -c "rm -rf /target/* /target/.[!.]* /target/..?*; tar -xzf /backup/${suffix}.tar.gz -C /target"
  done
  printf '%s\n' "RESTORE_STATUS=PASS" "AUTO_START=false"
}

case "$ACTION" in
  backup) backup ;;
  restore) restore ;;
  *) echo "usage: $0 {backup|restore} [backup_dir]"; exit 2 ;;
esac
read -r -p "Enterキーで終了します..." _
