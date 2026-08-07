#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="$ROOT/deploy/observability"
ENV_FILE="${OBSERVABILITY_ENV_FILE:-$DEPLOY/.env}"
[[ -f "$ENV_FILE" ]] || ENV_FILE="$DEPLOY/.env.example"
# shellcheck disable=SC1090
source "$ENV_FILE"

retry() {
  local url="$1"
  for _ in $(seq 1 60); do
    if curl --fail --silent --show-error --max-time 3 "$url" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "BLOCKED: endpoint not ready: $url" >&2
  return 1
}

retry "http://127.0.0.1:${GRAFANA_PORT:-3000}/api/health"
retry "http://127.0.0.1:${PROMETHEUS_PORT:-9090}/-/ready"
retry "http://127.0.0.1:${LOKI_PORT:-3100}/ready"
retry "http://127.0.0.1:${TEMPO_PORT:-3200}/ready"
retry "http://127.0.0.1:${ALLOY_PORT:-12345}/-/ready"

python - "http://127.0.0.1:${PROMETHEUS_PORT:-9090}/api/v1/targets" <<'PY_TARGETS'
from __future__ import annotations

import json
import sys
from urllib.request import urlopen

expected = {"prometheus", "alloy", "loki", "tempo", "grafana"}
with urlopen(sys.argv[1], timeout=5) as response:
    payload = json.load(response)
if payload.get("status") != "success":
    raise SystemExit("BLOCKED: Prometheus targets API did not return success")
active = payload["data"]["activeTargets"]
by_job = {item["labels"].get("job"): item.get("health") for item in active}
missing = expected - set(by_job)
unhealthy = {job: by_job.get(job) for job in expected if by_job.get(job) != "up"}
if missing or unhealthy:
    raise SystemExit(f"BLOCKED: missing={sorted(missing)} unhealthy={unhealthy}")
print(json.dumps({"status": "PASS", "targets": by_job}, indent=2, sort_keys=True))
PY_TARGETS

printf '%s\n' "SMOKE_STATUS=PASS"
