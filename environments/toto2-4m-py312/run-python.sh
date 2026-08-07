#!/usr/bin/env bash
set -Eeuo pipefail

ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ENV_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  printf 'BLOCKED: isolated Python does not exist: %s\n' "$PYTHON" >&2
  printf 'Run bootstrap-lock-candidate.sh and review the generated lock first.\n' >&2
  exit 2
fi

exec "$PYTHON" "$@"
