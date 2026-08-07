#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-gluonts-p7b-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${1:-${ROOT}/artifacts/gluonts-p7b/${RUN_ID}}"
shift $(( $# > 0 ? 1 : 0 ))

exec python3 "${ROOT}/environments/gluonts-p7b-supervisor.py" \
  --repo-root "${ROOT}" \
  --output "${OUT}" \
  --run-id "${RUN_ID}" \
  "$@"
